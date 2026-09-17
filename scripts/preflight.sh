#!/usr/bin/env bash
# Pre-install check. Run this on the server BEFORE docs/INSTALL.md.
#
# Changes nothing. Reads state and tells you what will bite you, so problems
# surface before the first sudo rather than halfway through phase 2.
set -uo pipefail

pass=0; warn=0; fail=0
ok()   { echo "  [ ok ]   $1"; pass=$((pass+1)); }
note() { echo "  [warn]   $1"; warn=$((warn+1)); }
bad()  { echo "  [FAIL]   $1"; fail=$((fail+1)); }

echo "Preflight check for the home server install"
echo "==========================================="
echo

echo "System"
source /etc/os-release 2>/dev/null || true
case "${VERSION_ID:-}" in
  20.04|22.04|24.04) ok "Ubuntu ${VERSION_ID}" ;;
  "")                bad "cannot read /etc/os-release" ;;
  *)                 note "Ubuntu ${VERSION_ID} — untested here, probably fine" ;;
esac

if [[ "$(whoami)" == "foe" ]]; then
  ok "running as foe"
else
  bad "running as $(whoami), not foe — paths in this repo assume /home/foe"
fi

[[ $EUID -ne 0 ]] && ok "not running as root" || bad "running as root — don't; use sudo per command"

pyver=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo none)
if [[ "$pyver" == "none" ]]; then
  bad "python3 not found — the bridge needs it"
elif python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)'; then
  ok "python3 ${pyver}"
else
  bad "python3 ${pyver} is too old — need 3.8+"
fi
echo

echo "Resources"
ram_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if   (( ram_mb >= 5000 )); then ok "RAM ${ram_mb}MB"
elif (( ram_mb >= 3000 )); then note "RAM ${ram_mb}MB — tight; skip n8n, and watch Ollama closely"
else                            bad "RAM ${ram_mb}MB — too small for this stack"
fi

disk_avail_gb=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
(( disk_avail_gb >= 20 )) && ok "disk ${disk_avail_gb}GB free" \
                          || bad "only ${disk_avail_gb}GB free — llama3.2 alone is ~2GB"

swap_mb=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
(( swap_mb > 0 )) && ok "swap present (${swap_mb}MB) — a cushion, not a plan" \
                  || note "no swap — an OOM will kill a container outright"
echo

echo "Network (nothing here will be changed)"
ip_addr=$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || echo unknown)
[[ "$ip_addr" != "unknown" ]] && ok "current IP ${ip_addr}" || bad "no default route — no network?"
iface=$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'dev \K\S+' || echo unknown)
[[ "$iface" != "unknown" ]] && ok "interface ${iface}" || true
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && ok "internet reachable" \
                                     || bad "no internet — the installs will fail"
echo

echo "SSH"
if [[ -f ~/.ssh/authorized_keys ]] && [[ -s ~/.ssh/authorized_keys ]]; then
  ok "authorized_keys present ($(grep -c . ~/.ssh/authorized_keys) key(s))"
  [[ "$(stat -c %a ~/.ssh)" == "700" ]] && ok "~/.ssh is 700" \
    || note "~/.ssh is $(stat -c %a ~/.ssh) — sshd may refuse it; want 700"
  [[ "$(stat -c %a ~/.ssh/authorized_keys)" == "600" ]] && ok "authorized_keys is 600" \
    || note "authorized_keys is $(stat -c %a ~/.ssh/authorized_keys) — want 600"
else
  bad "no authorized_keys — do NOT disable password auth until your key is installed"
fi
echo

echo "USB backup target"
if mountpoint -q /mnt/backup; then
  avail=$(df -h --output=avail /mnt/backup | tail -1 | tr -d ' ')
  ok "/mnt/backup mounted, ${avail} free"
else
  note "/mnt/backup not mounted yet — that's phase 3.1. Candidate devices:"
  lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,TRAN 2>/dev/null \
    | awk 'NR==1 || /usb/ || /sd[b-z]/' | sed 's/^/           /'
fi
echo

echo "Ports the install wants (occupied ones are a conflict)"
for port in 80 3001 5678 9000 11434; do
  if ss -tlnH "sport = :$port" 2>/dev/null | grep -q .; then
    note "port ${port} already in use by: $(ss -tlnpH "sport = :$port" 2>/dev/null | grep -oP '"\K[^"]+' | head -1)"
  else
    ok "port ${port} free"
  fi
done
echo

echo "Already installed?"
for cmd in docker restic ufw fail2ban-client ollama tailscale; do
  command -v "$cmd" >/dev/null && ok "${cmd} present" || note "${cmd} not installed yet"
done
echo

echo "==========================================="
echo "  ${pass} ok, ${warn} warnings, ${fail} failures"
if (( fail )); then
  echo
  echo "Fix the failures before starting docs/INSTALL.md."
  exit 1
fi
echo
echo "No blockers. Warnings above are things to know, not things to fix."
echo "Next: less docs/INSTALL.md"
