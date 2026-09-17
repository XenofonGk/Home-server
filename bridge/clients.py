"""HTTP clients for Telegram and Ollama.

Standard library only -- no pip install, no virtualenv to keep alive, nothing
to break on an unattended `apt upgrade`. urllib is enough for two endpoints.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class TransientError(Exception):
    """A failure worth retrying (network blip, 5xx, timeout)."""


class PermanentError(Exception):
    """A failure that will not improve by trying again (bad token, 4xx)."""


def _post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        if 500 <= exc.code < 600 or exc.code == 429:
            raise TransientError(f"HTTP {exc.code}: {detail}") from exc
        raise PermanentError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransientError(f"network error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TransientError(f"malformed JSON response: {exc}") from exc


class TelegramClient:
    """Minimal Telegram Bot API client.

    Note: only ONE process may call get_updates for a given bot token. Uptime
    Kuma also uses this token, but only to send -- sending and polling coexist
    fine. Adding a second poller (or a webhook) would make the two steal each
    other's updates. Do not add one.
    """

    def __init__(self, token: str, timeout_s: int = 30) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._timeout_s = timeout_s

    def get_updates(self, offset: Optional[int], poll_timeout_s: int) -> List[dict]:
        payload: Dict[str, Any] = {
            "timeout": poll_timeout_s,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        # Read timeout must outlast the long-poll or we cancel our own request.
        data = _post_json(
            f"{self._base}/getUpdates", payload, timeout=poll_timeout_s + 10
        )
        if not data.get("ok"):
            raise PermanentError(f"getUpdates returned not-ok: {data}")
        return data.get("result", [])

    def send_message(self, chat_id: int, text: str) -> None:
        data = _post_json(
            f"{self._base}/sendMessage",
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=self._timeout_s,
        )
        if not data.get("ok"):
            raise PermanentError(f"sendMessage returned not-ok: {data}")

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        """Best-effort 'typing' indicator. Never fatal -- it is a nicety."""
        try:
            _post_json(
                f"{self._base}/sendChatAction",
                {"chat_id": chat_id, "action": action},
                timeout=10,
            )
        except (TransientError, PermanentError):
            pass


class OllamaClient:
    """Talks to the local Ollama HTTP API on 127.0.0.1."""

    def __init__(self, url: str, model: str, timeout_s: int = 300) -> None:
        self._url = url
        self._model = model
        self._timeout_s = timeout_s

    def generate(self, prompt: str) -> str:
        data = _post_json(
            self._url,
            {"model": self._model, "prompt": prompt, "stream": False},
            timeout=self._timeout_s,
        )
        response = data.get("response")
        if not isinstance(response, str) or not response.strip():
            raise TransientError(f"no usable response field in reply: {data}")
        return response.strip()
