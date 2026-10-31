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

# What people type into a search engine for each game: the name in its page title, then the other names
# it goes by. Generic game names only (never another company's brand).
SEARCH: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "trivia": ("Trivia Quiz", ("pub quiz", "general knowledge quiz", "trivia night")),
    "rather": ("Would You Rather", ("would you rather questions", "this or that")),
    "frenemy": ("Most Likely To", ("who's most likely to", "ranking game", "friendship quiz")),
    "alibi": ("Murder Mystery", ("whodunit", "murder mystery party game", "find the killer")),
    "price": ("Guess the Price", ("price guessing game", "higher or lower")),
    "telepathy": ("Mind Reading Game", ("think alike", "great minds game", "majority vote game")),
    "mural": ("Find the Spy", ("spy game", "odd one out", "art bluffing game")),
    "blackjack": ("Blackjack", ("21", "twenty-one", "card game with friends")),
    "crossword": ("Crossword Race", ("multiplayer crossword", "crossword puzzle")),
    "dice": ("Liar's Dice", ("bluff dice", "dudo", "dice bluffing game")),
    "split": ("Split or Steal", ("prisoner's dilemma game", "trust game")),
    "chicken": ("Push Your Luck", ("cash out game", "chicken game", "bomb timer game")),
    "wits": ("Guess and Bet Trivia", ("betting quiz", "number guessing quiz")),
    "codes": ("Code Breaker", ("bulls and cows", "crack the code", "code breaking game")),
    "roulette": ("Roulette", ("roulette wheel", "spin the wheel")),
    "lonely": ("Lowest Unique Number", ("unique number game", "number bluff")),
    "boxes": ("Mystery Box Auction", ("auction game", "bidding game", "mystery box")),
    "codewords": ("Spymaster Word Game", ("word association game", "team word game", "spymaster")),
    "truthdare": ("Truth or Dare", ("truth or dare questions", "spin the bottle")),
    "wordrace": (
        "Five-Letter Word Game",
        ("guess the word in six tries", "daily word game", "word guessing"),
    ),
    "lastcard": ("Last Card", ("crazy eights", "colour matching card game", "switch")),
    "ludo": ("Ludo", ("pachisi", "ludo online", "ludo with friends")),
    "chess": ("Chess", ("chess with friends", "chess online")),
    "drawguess": ("Draw and Guess", ("drawing game", "draw and guess online", "sketch and guess")),
    "telephone": ("Draw Telephone", ("telephone drawing game", "broken telephone", "draw and describe")),
    "tycoon": ("Property Trading Game", ("property board game", "real estate board game", "trading game")),
    "mafia": ("Mafia", ("werewolf", "mafia party game", "social deduction game")),
    "bomb": ("Hot Potato", ("word bomb", "pass the bomb", "word chain game")),
    "reflex": ("Reaction Time Game", ("reflex test", "fastest finger", "quick draw")),
    "snakes": ("Snakes and Ladders", ("snakes and ladders online", "ladders board game")),
    "ships": ("Battleships", ("battleship game", "sea battle", "sink the fleet")),
    "four": ("Four in a Row", ("four in a line", "drop four", "line up four")),
    "lists": ("Category Game", ("name place animal thing", "stop the bus", "categories game")),
    "hangman": ("Hangman", ("hangman word game", "guess the word")),
    "fivedice": ("Five Dice", ("dice poker", "yacht dice", "five dice game")),
    "onhead": ("Forehead Guessing Game", ("charades", "who am I", "guess the word on your head")),
    "imposter": ("Imposter Game", ("who is the imposter", "undercover word game", "find the spy")),
}

# Shown first to new players: learned in a minute, good with people you just met, one of each kind of fun.
FEATURED: Final = ("imposter", "trivia", "drawguess", "rather", "dice", "four")

# Games where the better player wins most of the time, so a rating means something. Luck and opinion
# games stay unranked (they still pay coins by place).
RANKED: Final = frozenset(
    {"trivia", "wordrace", "crossword", "codewords", "dice", "codes", "reflex", "chess", "four", "ships"}
)
# A ranked game needs 2 players for a duel, 3 for a free-for-all (fewer can't separate skill from luck).
DUELS: Final = frozenset({"chess", "four", "ships", "reflex"})


def ranked_min(game_id: str) -> int | None:
    if game_id not in RANKED:
        return None
    return 2 if game_id in DUELS else 3


def entry(game_id: str) -> dict[str, object]:
    """The catalogue fields a game card carries."""
    return {
        "category": CATEGORY_OF[game_id],
        "featured": FEATURED.index(game_id) if game_id in FEATURED else None,
        "ranked": game_id in RANKED,
        "ranked_min": ranked_min(game_id),
        "search": SEARCH[game_id][0],
        "aka": list(SEARCH[game_id][1]),
    }


@cache
def categories() -> list[dict[str, str]]:
    return [
        {"id": cid, "label": label, "title": title, "blurb": blurb} for cid, label, title, blurb in CATEGORIES
    ]
