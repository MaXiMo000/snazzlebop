"""The jump-scare prank: a private list of names (from the environment, never the repo) whose owners get a
ghost and a scream when they join and when scores come up. Matching is deliberately forgiving: any
capitalisation, accents, look-alike digits (Ea7y, 3azy), doubled letters (Rayyy) and one slip of a
letter (Eazi, Elza), on any single word of the name.

Pure functions only. Names are compared, never stored or logged.
"""

from __future__ import annotations

import re
import unicodedata

LEET = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
        "9": "g",
        "@": "a",
        "$": "s",
        "!": "i",
    }
)


def fold(text: str) -> str:
    """Lower-case letters only: accents dropped, look-alike digits turned back into letters, doubled
    letters collapsed (so 'RAYYY' and 'Ray' meet)."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text)).casefold().translate(LEET)
    letters = "".join(ch for ch in text if ch.isalpha() and not unicodedata.combining(ch))
    return re.sub(r"(.)\1+", r"\1", letters)


def close(a: str, b: str) -> bool:
    """Equal, or one letter added, removed or swapped for another."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def targets(raw: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(t for t in dict.fromkeys(fold(x) for x in raw) if len(t) >= 2)


def matches(name: str, wanted: tuple[str, ...]) -> bool:
    """Does any word of this display name (or the whole name squashed together) match a target?"""
    if not wanted:
        return False
    words = [fold(w) for w in re.split(r"[\s._\-']+", name)]
    candidates = {w for w in words if w} | {fold(name)}
    for want in wanted:
        for cand in candidates:
            # Two-letter targets must match exactly; one slip there would catch half the alphabet.
            if cand == want or (len(want) >= 3 and len(cand) >= 3 and close(cand, want)):
                return True
    return False
