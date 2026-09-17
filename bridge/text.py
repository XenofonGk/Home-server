"""Pure text helpers. No I/O, so this is the easy part to test."""

from __future__ import annotations

from typing import List


def split_message(text: str, limit: int = 4096) -> List[str]:
    """Split text into chunks that fit Telegram's per-message limit.

    Prefers to break on paragraph, then line, then word boundaries so replies
    do not get chopped mid-word. Falls back to a hard cut for pathological
    input (a single token longer than the limit, e.g. a base64 blob).
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    remaining = text

    while len(remaining) > limit:
        window = remaining[:limit]
        # Try progressively weaker break points.
        for separator in ("\n\n", "\n", " "):
            cut = window.rfind(separator)
            if cut > 0:
                break
        else:
            cut = -1

        if cut <= 0:
            cut = limit  # hard cut; nothing better available

        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def truncate_for_log(text: str, limit: int = 200) -> str:
    """Shorten text for the log. Logs are not a transcript store."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"
