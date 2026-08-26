"""
PLATFORM: Prompt loader — reads system prompt from prompts/system.txt.

Usage:
    from src.prompts import load_prompt, reload

    text = load_prompt()                        # cached file read
    text = load_prompt(override_text="custom")   # use override instead
    reload()                                     # force re-read from disk
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.txt"
_cached_prompt: str | None = None


def _read_prompt_file() -> str:
    """Read the system prompt file from disk."""
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_prompt(override_text: str | None = None) -> str:
    """Return the system prompt.

    If *override_text* is provided, return it directly (used by /evaluate).
    Otherwise return the cached file contents from prompts/system.txt.
    """
    if override_text is not None:
        return override_text

    global _cached_prompt  # noqa: PLW0603
    if _cached_prompt is None:
        _cached_prompt = _read_prompt_file()
    return _cached_prompt


def reload() -> str:
    """Force re-read the prompt file from disk and return the new text."""
    global _cached_prompt  # noqa: PLW0603
    _cached_prompt = _read_prompt_file()
    return _cached_prompt
