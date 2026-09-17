#!/usr/bin/env bash
# Prove the backup is restorable: pull one volume out of the newest snapshot
# into a scratch directory and diff it against the live copy.
#
# An untested backup is not a backup. Run this after the first backup, and
# any time you change what gets backed up.
set -euo pipefail

RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-/mnt/backup/restic}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/home/foe/server/.restic-password}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

VOLUME="${1:-uptime-kuma_uptime-kuma-data}"
SOURCE="/var/lib/docker/volumes/${VOLUME}"
SCRATCH="$(mktemp -d /tmp/restore-verify.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

mountpoint -q /mnt/backup || { echo "/mnt/backup is not mounted" >&2; exit 1; }
[[ -d "$SOURCE" ]] || { echo "no such volume: $SOURCE" >&2; exit 1; }

echo "restoring ${VOLUME} from the latest snapshot into ${SCRATCH}"
restic restore latest --target "$SCRATCH" --include "$SOURCE"

echo
echo "diffing restored copy against live data:"
if sudo diff -r "$SOURCE" "${SCRATCH}${SOURCE}"; then
  echo
  echo "RESTORE VERIFIED: restored data is identical to live data."
else
  echo
  echo "Differences found. If the service was running during the backup a few"
  echo "byte-level differences in a live database file are expected; anything"
  echo "structural means the backup is not trustworthy. Investigate." >&2
  exit 1
fi
