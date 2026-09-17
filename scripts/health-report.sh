#!/usr/bin/env bash
# Daily health report over Telegram: disk, RAM, swap, containers, backup age.
# Alerts loudly when a threshold is crossed; otherwise sends a quiet summary.
#
# Run from cron as foe. See README for the crontab line.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTIFY="${HERE}/notify.sh"

DISK_WARN_PCT=80
SWAP_WARN_MB=256
BACKUP_STAMP="${BACKUP_STAMP:-/home/foe/server/.last-backup-ok}"
BACKUP_MAX_AGE_H=48

problems=()

# --- disk ---------------------------------------------------------------
disk_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
disk_human=$(df -h --output=avail / | tail -1 | tr -d ' ')
if (( disk_pct >= DISK_WARN_PCT )); then
  problems+=("Disk at ${disk_pct}% (only ${disk_human} free)")
fi

# --- memory -------------------------------------------------------------
mem_avail_mb=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
swap_total_mb=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
swap_free_mb=$(awk '/SwapFree/ {print int($2/1024)}' /proc/meminfo)
swap_used_mb=$(( swap_total_mb - swap_free_mb ))
if (( swap_used_mb >= SWAP_WARN_MB )); then
  problems+=("Swap in use: ${swap_used_mb}MB (RAM pressure -- something is too big for this box)")
fi

# --- containers ---------------------------------------------------------
expected=(uptime-kuma portainer nginx n8n)
down=()
for name in "${expected[@]}"; do
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
    down+=("$name")
  fi
done
(( ${#down[@]} )) && problems+=("Containers not running: ${down[*]}")

# --- bridge + ollama ----------------------------------------------------
systemctl is-active --quiet telegram-ollama-bridge || problems+=("Telegram bridge is not running")
systemctl is-active --quiet ollama || problems+=("Ollama is not running")

# --- backup freshness ---------------------------------------------------
# Catches the case the USB stick is unplugged: the stamp stops advancing.
if [[ -f "$BACKUP_STAMP" ]]; then
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$BACKUP_STAMP") ) / 3600 ))
  if (( age_h >= BACKUP_MAX_AGE_H )); then
    problems+=("Last successful backup was ${age_h}h ago (is the USB stick plugged in?)")
  fi
else
  problems+=("No successful backup has ever been recorded")
fi

# --- report -------------------------------------------------------------
summary="Disk ${disk_pct}% used, ${disk_human} free
RAM available ${mem_avail_mb}MB, swap used ${swap_used_mb}MB
Containers up: $(( ${#expected[@]} - ${#down[@]} ))/${#expected[@]}"

if (( ${#problems[@]} )); then
  body="PROBLEMS on home server:"
  for p in "${problems[@]}"; do body+=$'\n'"- ${p}"; done
  body+=$'\n\n'"${summary}"
  "$NOTIFY" "$body"
  exit 1
fi

"$NOTIFY" "Home server OK.

${summary}"
