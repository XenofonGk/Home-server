#!/usr/bin/env bash
# Send a Telegram message. Sourced by the other scripts so there is exactly
# one place that knows how to talk to the bot.
#
# Usage: notify.sh "message text"
set -euo pipefail

ENV_FILE="${BRIDGE_ENV_FILE:-/home/foe/server/bridge/.env}"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "notify: cannot read $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${TELEGRAM_BOT_TOKEN:?not set in $ENV_FILE}"
: "${TELEGRAM_ALLOWED_CHAT_IDS:?not set in $ENV_FILE}"

# Alerts go to the first ID in the allowlist.
CHAT_ID="${TELEGRAM_ALLOWED_CHAT_IDS%%[, ]*}"
MESSAGE="${1:?usage: notify.sh <message>}"

# --fail so a 4xx is an error, not a silent success. Retry once.
for attempt in 1 2; do
  if curl -sS --fail --max-time 20 \
      -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${CHAT_ID}" \
      --data-urlencode "text=${MESSAGE}" \
      -o /dev/null; then
    exit 0
  fi
  echo "notify: attempt ${attempt} failed" >&2
  [[ $attempt -eq 1 ]] && sleep 5
done

echo "notify: giving up after 2 attempts" >&2
exit 1
