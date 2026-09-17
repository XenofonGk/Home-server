#!/usr/bin/env bash
# Post-install verification. Run after docs/INSTALL.md, and any time you want
# to know the box is still in the shape you left it.
#
# Read-only. Checks the things that are easy to believe are true and easy to
# be wrong about: what's listening, what's exposed, what's enabled at boot.
set -uo pipefail

pass=0; fail=0
ok()  { echo "  [ ok ]   $1"; pass=$((pass+1)); }
bad() { echo "  [FAIL]   $1"; fail=$((fail+1)); }

echo "Home server verification — $(date -Is)"
echo "==============================================="
echo

echo "Network unchanged (this is the one that broke the machine last time)"
ip_addr=$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || echo unknown)
echo "         current IP: ${ip_addr}"
if nmcli -t -f ipv4.method con show "$(nmcli -t -f NAME con show --active | head -1)" 2>/dev/null | grep -q manual; then
  bad "connection is set to MANUAL ipv4 — a static IP was configured somewhere"
else
  ok "ipv4 still on DHCP (no static IP pinned)"
fi
echo

echo "SSH"
if sudo -n sshd -T >/dev/null 2>&1; then
  sudo -n sshd -T 2>/dev/null | grep -q '^passwordauthentication no' \
    && ok "password auth disabled" || bad "password auth still ENABLED"
  sudo -n sshd -T 2>/dev/null | grep -q '^permitrootlogin no' \
    && ok "root login disabled" || bad "root login still permitted"
else
  echo "  [skip]   needs sudo; run: sudo sshd -T | grep -E 'passwordauth|permitroot'"
fi
echo

echo "Ollama is loopback-only (it has no authentication of its own)"
if ss -tlnH 'sport = :11434' 2>/dev/null | grep -q .; then
  if ss -tlnH 'sport = :11434' | grep -qE '127\.0\.0\.1:11434|\[::1\]:11434'; then
    ok "bound to loopback only"
  else
    bad "listening on $(ss -tlnH 'sport = :11434' | awk '{print $4}' | head -1) — EXPOSED to the LAN"
  fi
else
  bad "nothing listening on 11434 — Ollama is not running"
fi
echo

echo "Firewall"
if sudo -n ufw status >/dev/null 2>&1; then
  sudo -n ufw status | grep -q '^Status: active' && ok "UFW active" || bad "UFW is INACTIVE"
  sudo -n ufw status | grep -q '^22' && ok "port 22 allowed (you can still get in)" \
                                     || bad "port 22 NOT allowed — you may be locked out on reconnect"
  sudo -n ufw status | grep -qE '^3000' && bad "port 3000 open but nothing should be there" \
                                        || ok "port 3000 correctly closed"
else
  echo "  [skip]   needs sudo; run: sudo ufw status verbose"
fi
echo

echo "Services enabled at boot"
for unit in docker ollama telegram-ollama-bridge fail2ban; do
  state=$(systemctl is-enabled "$unit" 2>/dev/null || echo missing)
  [[ "$state" == "enabled" ]] && ok "${unit}: enabled" || bad "${unit}: ${state}"
done
echo

echo "Containers"
for name in uptime-kuma portainer nginx n8n; do
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
    ok "${name} running"
  else
    bad "${name} not running"
  fi
done
echo

echo "Memory against the 4.5GB ceiling"
free -m | awk '/^Mem:/ {printf "         total %sMB, used %sMB, available %sMB\n", $2, $3, $7}'
free -m | awk '/^Swap:/ {printf "         swap used %sMB\n", $3}'
used_mb=$(free -m | awk '/^Mem:/ {print $3}')
(( used_mb < 4500 )) && ok "under the ceiling (${used_mb}MB)" \
                     || bad "over the ceiling (${used_mb}MB) — something needs to go"
echo "         per container:"
docker stats --no-stream --format '           {{.Name}}\t{{.MemUsage}}' 2>/dev/null || true
echo

echo "Backups"
stamp=/home/foe/server/.last-backup-ok
if [[ -f "$stamp" ]]; then
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$stamp") ) / 3600 ))
  (( age_h < 48 )) && ok "last successful backup ${age_h}h ago" \
                   || bad "last successful backup ${age_h}h ago — stale"
else
  bad "no successful backup recorded yet"
fi
mountpoint -q /mnt/backup && ok "/mnt/backup mounted" || bad "/mnt/backup not mounted (stick unplugged?)"
echo

echo "==============================================="
echo "  ${pass} ok, ${fail} failures"
(( fail )) && { echo; echo "Failures above are real. Fix them."; exit 1; }
echo
echo "Everything checks out."
