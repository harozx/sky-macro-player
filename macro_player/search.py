"""Accent-insensitive text matching for Vietnamese song titles."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^0-9a-z]+")


def fold_text(value: str) -> str:
    """Return lowercase ASCII words: ``"Bâng Khuâng (Fin)"`` -> ``"bang khuang fin"``.

    Vietnamese ``đ`` has no Unicode decomposition, so it is mapped explicitly.
    Characters without an ASCII base (for example CJK) are kept as-is.
    """
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = []
    for word in stripped.split():
        ascii_word = _NON_WORD.sub(" ", word).strip()
        words.append(ascii_word if ascii_word or word.isascii() else word)
    return " ".join(" ".join(words).split())


def matches(query: str, *texts: str) -> bool:
    """True when every query word occurs in one of ``texts`` (accents ignored).

    A query typed without spaces also matches a spaced title, so ``bangkhuang``
    finds *Bâng khuâng*.
    """
    needle = fold_text(query)
    if not needle:
        return True
    haystacks = [fold_text(text) for text in texts if text]
    if any(all(word in hay for word in needle.split()) for hay in haystacks):
        return True
    compact = needle.replace(" ", "")
    return any(compact in hay.replace(" ", "") for hay in haystacks)
