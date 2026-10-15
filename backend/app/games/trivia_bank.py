"""Trivia Tonight's question bank: trivia.txt, parsed and checked once at import.

Every question is {"cat", "level", "q", "a", "wrong"}: `a` is the right answer, `wrong` the other
choices (three for multiple choice, one for true-or-false). A malformed line, an unknown category,
a repeated choice or a duplicate question fails the import, so a bad edit never reaches a game.
Generated questions (contentgen) are appended to TRIVIA at runtime with the same shape.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# id -> (label, icon). The order is the lobby's order.
CATEGORIES: dict[str, tuple[str, str]] = {
    "general": ("General knowledge", "💡"),
    "science": ("Science", "🔬"),
    "geography": ("Geography", "🌍"),
    "history": ("History", "🏛️"),
    "screen": ("Movies & TV", "🎬"),
    "music": ("Music", "🎵"),
    "sport": ("Sport", "🏅"),
    "food": ("Food & drink", "🍜"),
    "animals": ("Animals", "🦁"),
    "space": ("Space", "🚀"),
    "words": ("Words & language", "🔤"),
    "arts": ("Art & books", "🎨"),
    "tech": ("Tech & inventions", "💻"),
    "myths": ("Myths & legends", "🐉"),
    "maths": ("Numbers", "🔢"),
}
LEVELS = (1, 2, 3)
TF = ("True", "False")


def question_key(q: str) -> str:
    return re.sub(r"[^a-z0-9]", "", q.casefold())


def parse(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    cat = ""
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            cat = line[1:-1]
            if cat not in CATEGORIES:
                raise ValueError(f"trivia.txt:{n}: unknown category {cat!r}")
            continue
        parts = [p.strip() for p in line.split("|")]
        if not cat or not parts[0].isdigit() or int(parts[0]) not in LEVELS or not all(parts):
            raise ValueError(f"trivia.txt:{n}: bad line")
        level, q = int(parts[0]), parts[1]
        if len(parts) == 3 and parts[2] in TF:
            a, wrong = parts[2], [TF[1] if parts[2] == TF[0] else TF[0]]
        elif len(parts) == 6:
            a, wrong = parts[2], parts[3:]
            if len({c.casefold() for c in parts[2:]}) != 4:
                raise ValueError(f"trivia.txt:{n}: repeated choice")
        else:
            raise ValueError(f"trivia.txt:{n}: expected 3 or 6 fields")
        key = question_key(q)
        if key in seen:
            raise ValueError(f"trivia.txt:{n}: duplicate question")
        seen.add(key)
        out.append({"cat": cat, "level": level, "q": q, "a": a, "wrong": wrong})
    return out


TRIVIA: list[dict[str, Any]] = parse((Path(__file__).with_name("trivia.txt")).read_text(encoding="utf-8"))
