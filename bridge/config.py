"""Configuration for the Telegram/Ollama bridge, loaded from the environment.

Kept separate from the network code so tests can build a Config directly
without touching os.environ or the filesystem.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(Exception):
    """Raised when the environment is missing something we cannot default."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    # Only these chat IDs get a reply. Everything else is dropped.
    allowed_chat_ids: frozenset[int]
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "llama3.2"
    # Telegram hard-caps messages at 4096 characters.
    max_message_chars: int = 4096
    # How long to long-poll Telegram for updates.
    poll_timeout_s: int = 30
    # Generation can be slow on CPU. This is the ceiling before we give up
    # and tell the user, rather than hanging forever.
    ollama_timeout_s: int = 300
    log_path: str = "/home/foe/server/logs/bridge.log"

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if env is None else env)

        token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is not set")

        raw_ids = env.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
        if not raw_ids:
            # Refusing to start is the correct behaviour here. A bridge with an
            # empty allowlist would hand free inference to anyone who finds the
            # bot, and "fail open" is exactly the bug we are avoiding.
            raise ConfigError(
                "TELEGRAM_ALLOWED_CHAT_IDS is not set. Refusing to start with an "
                "empty allowlist -- that would let any Telegram user run inference "
                "on this machine."
            )

        try:
            ids = frozenset(int(part) for part in raw_ids.replace(",", " ").split())
        except ValueError as exc:
            raise ConfigError(
                f"TELEGRAM_ALLOWED_CHAT_IDS must be integers, got {raw_ids!r}"
            ) from exc

        if not ids:
            raise ConfigError("TELEGRAM_ALLOWED_CHAT_IDS parsed to an empty set")

        return Config(
            bot_token=token,
            allowed_chat_ids=ids,
            ollama_url=env.get("OLLAMA_URL", Config.ollama_url),
            ollama_model=env.get("OLLAMA_MODEL", Config.ollama_model),
            log_path=env.get("BRIDGE_LOG_PATH", Config.log_path),
        )

    def is_allowed(self, chat_id: int) -> bool:
        return chat_id in self.allowed_chat_ids
