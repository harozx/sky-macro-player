"""Lightweight UI translation: Vietnamese source strings, optional English.

Every user-visible string is written in Vietnamese and passed through ``tr``.
Strings evaluated at import time (module constants) are marked with ``N_`` and
translated where they are displayed. The language is chosen once at start-up,
before any widget is built, so switching takes effect after a restart.
"""

from __future__ import annotations

from .i18n_en import EN

DEFAULT_LANGUAGE = "vi"
# Language names are shown in their own language so anyone can find theirs.
LANGUAGES = {"vi": "Tiếng Việt", "en": "English"}

_language = DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    global _language
    _language = code if code in LANGUAGES else DEFAULT_LANGUAGE


def language() -> str:
    return _language


def tr(text: str) -> str:
    """Return ``text`` in the active language (Vietnamese when untranslated)."""
    if _language == "en":
        return EN.get(text, text)
    return text


def N_(text: str) -> str:
    """Mark a constant for translation without translating it yet."""
    return text
