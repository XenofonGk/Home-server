#!/usr/bin/env bash
# Nightly restic backup to the USB stick.
#
# Backs up Docker volume data, the compose files, the bridge, and the setup
# log. Touches a stamp file on success so health-report.sh can notice when
# backups quietly stop (e.g. the stick was unplugged).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTIFY="${HERE}/notify.sh"

RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-/mnt/backup/restic}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/home/foe/server/.restic-password}"
STAMP="${BACKUP_STAMP:-/home/foe/server/.last-backup-ok}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

fail() {
  echo "backup failed: $1" >&2
  "$NOTIFY" "BACKUP FAILED on home server: $1" || true
  exit 1
}

# The stick is mounted with nofail, so a missing mount is a normal-ish state
# we must detect rather than silently backing up to the root filesystem --
# which would fill the disk and look like it worked.
mountpoint -q /mnt/backup || fail "/mnt/backup is not mounted (USB stick unplugged?)"
[[ -r "$RESTIC_PASSWORD_FILE" ]] || fail "cannot read $RESTIC_PASSWORD_FILE"

restic snapshots >/dev/null 2>&1 || restic init || fail "could not open or init repo"

# Docker named volumes live here. Copying them hot is fine for these
# services (SQLite with WAL, no large write volume at 03:00) but stopping
# them is strictly safer, so we do that -- downtime is a few seconds.
docker compose -f /home/foe/server/services/uptime-kuma/docker-compose.yml stop >/dev/null 2>&1 || true
docker compose -f /home/foe/server/services/n8n/docker-compose.yml stop >/dev/null 2>&1 || true

restart_services() {
  docker compose -f /home/foe/server/services/uptime-kuma/docker-compose.yml start >/dev/null 2>&1 || true
  docker compose -f /home/foe/server/services/n8n/docker-compose.yml start >/dev/null 2>&1 || true
}
trap restart_services EXIT

restic backup \
  --tag nightly \
  --exclude-caches \
  /var/lib/docker/volumes \
  /home/foe/server \
  /home/foe/server-setup-log.md \
  || fail "restic backup returned non-zero"

restic forget --tag nightly \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 6 \
  --prune || fail "restic forget/prune failed"

restic check --read-data-subset=5% || fail "restic check found repository problems"

touch "$STAMP"
echo "backup ok: $(date -Is)"
