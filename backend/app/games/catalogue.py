"""The game catalogue as data: which category each game sits in, the "Start here" row for newcomers, and
which games can be ranked. The lobby shelf, club settings and ranked queues read this, so the shelf can
change without touching a game. Every registered game must have an entry (tests check it)."""

from __future__ import annotations

from functools import cache
from typing import Final

# (id, chip label, title, what it feels like), in shelf order.
CATEGORIES: Final = (
    ("party", "Party", "Party and ice-breakers", "Talk, laugh and learn about each other. No skill needed."),
    ("quiz", "Quiz and words", "Quiz and words", "Knowledge and wordplay."),
    ("bluff", "Bluff", "Bluff and mind games", "Read people, deceive, outthink."),
    ("nerve", "Nerve", "Nerve and game-show", "Risk, timing and big swings."),
    ("classics", "Classics", "Board and card classics", "Games everyone already knows."),
)

CATEGORY_OF: Final[dict[str, str]] = {
    # party and ice-breakers
    "imposter": "party",
    "rather": "party",
    "truthdare": "party",
    "onhead": "party",
    "frenemy": "party",
    "drawguess": "party",
    "telephone": "party",
    "mural": "party",
    "bomb": "party",
    # quiz and words
    "trivia": "quiz",
    "wordrace": "quiz",
    "lists": "quiz",
    "hangman": "quiz",
    "crossword": "quiz",
    "codewords": "quiz",
    # bluff and mind games
    "dice": "bluff",
    "mafia": "bluff",
    "alibi": "bluff",
    "telepathy": "bluff",
    "split": "bluff",
    "codes": "bluff",
    "lonely": "bluff",
    # nerve and game-show
    "chicken": "nerve",
    "price": "nerve",
    "wits": "nerve",
    "roulette": "nerve",
    "boxes": "nerve",
    "blackjack": "nerve",
    "reflex": "nerve",
    # board and card classics
    "chess": "classics",
    "four": "classics",
    "ships": "classics",
    "ludo": "classics",
    "snakes": "classics",
    "lastcard": "classics",
    "fivedice": "classics",
    "tycoon": "classics",
}

# Shown first to new players: learned in a minute, good with people you just met, one of each kind of fun.
FEATURED: Final = ("imposter", "trivia", "drawguess", "rather", "dice", "four")

# Games where the better player wins most of the time, so a rating means something. Luck and opinion
# games stay unranked (they still pay coins by place).
RANKED: Final = frozenset(
    {"trivia", "wordrace", "crossword", "codewords", "dice", "codes", "reflex", "chess", "four", "ships"}
)


def entry(game_id: str) -> dict[str, object]:
    """The catalogue fields a game card carries."""
    return {
        "category": CATEGORY_OF[game_id],
        "featured": FEATURED.index(game_id) if game_id in FEATURED else None,
        "ranked": game_id in RANKED,
    }


@cache
def categories() -> list[dict[str, str]]:
    return [
        {"id": cid, "label": label, "title": title, "blurb": blurb} for cid, label, title, blurb in CATEGORIES
    ]
