"""Fair play: the rules that stop coins, prizes and ratings being farmed. Pure.

Every payout (game coins, battle prizes, rating changes) passes these checks, so the limits can't be
dodged by switching from one way of earning to another:

- too quick: a game that ends within MIN_GAME_SECONDS of starting pays nothing (thrown games);
- repeat group: the exact same set of accounts stops earning after REPEAT_LIMIT paid games in 24 hours
  (two friends, or a ring of alts, playing each other over and over);
- alone with guests: place coins need at least one other signed-in account in the game; without one,
  everyone gets the finisher amount (playing against your own guest tab);
- same device: accounts that have signed in on the same browser earn nothing against each other;
- seated at the start: only accounts in their seat when the game began are paid;
- new accounts: battle prizes need an account NEW_ACCOUNT_DAYS old with a confirmed email or Google.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

MIN_GAME_SECONDS = 45
REPEAT_LIMIT = 5  # paid games a day with exactly the same accounts
BATTLE_REPEAT_LIMIT = 3  # paid battles a day with exactly the same accounts
SOLO_COINS = 5  # place coins without another signed-in player: everyone gets the finisher amount
NEW_ACCOUNT_DAYS = 3

# Held-back reasons that also keep a game out of XP, quests and "new connections".
UNFAIR = frozenset({"quick", "device", "repeat", "solo"})

# Why a payout was held back, as players are told.
NOTES = {
    "limit": "today's limit is reached",
    "repeat": "this group already played a lot today",
    "device": "these accounts share a device",
    "quick": "the game ended too quickly",
    "solo": "no other signed-in player",
    "new": "new accounts can win prizes after 3 days, with a confirmed email",
    "left": "left before the end",
}


def group_key(accounts: Iterable[int]) -> str:
    """The same set of accounts gives the same key, in any order."""
    ids = ",".join(str(a) for a in sorted(set(accounts)))
    return hashlib.sha256(ids.encode()).hexdigest()[:32]


def too_quick(seconds: float) -> bool:
    return seconds < MIN_GAME_SECONDS


def solo_coins(coins: int, accounts: int) -> tuple[int, str]:
    """Place coins need another signed-in player in the game."""
    if accounts >= 2 or coins <= SOLO_COINS:
        return coins, ""
    return SOLO_COINS, "solo"
