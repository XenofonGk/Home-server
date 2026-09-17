"""Telegram <-> Ollama bridge daemon.

Long-polls Telegram for messages from an allowlisted chat, forwards them to
the local Ollama API, and sends the reply back. Runs under systemd as the
user 'foe'.

Deliberately NOT a chat with memory: each message is a fresh prompt. Adding
conversation history would mean storing message content on disk, which is a
bigger decision than this daemon should make on its own.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
import time
from typing import Optional

from .clients import (
    OllamaClient,
    PermanentError,
    TelegramClient,
    TransientError,
)
from .config import Config, ConfigError
from .retry import retry_with_backoff
from .text import split_message, truncate_for_log

log = logging.getLogger("bridge")

# Shown when Ollama is unreachable or still loading the model. Better than a
# silent hang -- the whole point is knowing the box is alive.
BUSY_NOTICE = (
    "The model is not responding right now. It may still be loading "
    "(first request after an idle period takes longer), or Ollama may be down. "
    "Try again in a moment."
)


def extract_message(update: dict) -> Optional[tuple]:
    """Pull (chat_id, text) out of a Telegram update, or None if unusable."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or "id" not in chat:
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return int(chat["id"]), text.strip()


def handle_update(
    update: dict,
    config: Config,
    telegram: TelegramClient,
    ollama: OllamaClient,
) -> str:
    """Process one update. Returns a short status string for logging/tests.

    Never raises for an expected failure -- a bad message must not take the
    daemon down.
    """
    parsed = extract_message(update)
    if parsed is None:
        return "ignored:unusable"

    chat_id, text = parsed

    if not config.is_allowed(chat_id):
        # Log it, drop it, do not reply. Replying would confirm the bot is
        # live to whoever is probing it.
        log.warning("rejected message from non-allowlisted chat_id=%s", chat_id)
        return "rejected:not_allowlisted"

    log.info("prompt from chat_id=%s: %s", chat_id, truncate_for_log(text))
    telegram.send_chat_action(chat_id, "typing")

    try:
        reply = retry_with_backoff(
            lambda: ollama.generate(text),
            attempts=2,
            base_delay_s=2.0,
            exceptions=(TransientError,),
        )
    except (TransientError, PermanentError) as exc:
        log.error("ollama failed for chat_id=%s: %s", chat_id, exc)
        _send_safely(telegram, chat_id, BUSY_NOTICE)
        return "error:ollama"

    chunks = split_message(reply, config.max_message_chars)
    for chunk in chunks:
        if not _send_safely(telegram, chat_id, chunk):
            return "error:telegram"

    log.info("replied to chat_id=%s in %d message(s)", chat_id, len(chunks))
    return "ok"


def _send_safely(telegram: TelegramClient, chat_id: int, text: str) -> bool:
    """Send with one retry. Logs loudly on failure rather than raising."""
    try:
        retry_with_backoff(
            lambda: telegram.send_message(chat_id, text),
            attempts=2,
            base_delay_s=2.0,
            exceptions=(TransientError,),
        )
        return True
    except (TransientError, PermanentError) as exc:
        log.error("telegram delivery failed for chat_id=%s: %s", chat_id, exc)
        return False


def configure_logging(log_path: str) -> None:
    """Rotating file log. cron and systemd both swallow stdout."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    # Also to stdout so `journalctl -u telegram-ollama-bridge` is useful.
    log.addHandler(logging.StreamHandler(sys.stdout))


def run() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1

    configure_logging(config.log_path)
    log.info(
        "bridge starting: model=%s allowlist=%d chat id(s)",
        config.ollama_model,
        len(config.allowed_chat_ids),
    )

    telegram = TelegramClient(config.bot_token)
    ollama = OllamaClient(config.ollama_url, config.ollama_model, config.ollama_timeout_s)

    running = True

    def stop(signum, _frame):
        nonlocal running
        log.info("received signal %s, shutting down", signum)
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    offset: Optional[int] = None
    backoff = 1.0

    while running:
        try:
            updates = telegram.get_updates(offset, config.poll_timeout_s)
            backoff = 1.0
        except TransientError as exc:
            log.warning("getUpdates transient failure: %s (retrying in %.0fs)", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
            continue
        except PermanentError as exc:
            # A bad token will not fix itself. Exit non-zero and let systemd
            # surface it rather than spinning forever.
            log.error("getUpdates permanent failure: %s", exc)
            return 1

        for update in updates:
            # Advance the offset even for updates we reject, so a hostile
            # sender cannot wedge the queue by repeating a bad message.
            offset = update["update_id"] + 1
            try:
                handle_update(update, config, telegram, ollama)
            except Exception:  # noqa: BLE001 -- last line of defence
                log.exception("unexpected error handling update %s", update.get("update_id"))

    log.info("bridge stopped")
    return 0


if __name__ == "__main__":
    sys.exit(run())
