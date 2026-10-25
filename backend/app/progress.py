"""Levels and daily quests. Pure.

XP comes only from fair games (fairplay.py: two or more signed-in players, not too quick, no shared
device, not the same group over and over), up to a daily cap, plus finished quests. Each level pays coins
and a random power-up, once. Each day brings three quests, always one that means playing with someone
new: the product's goal is people meeting through games.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date

XP_FINISH = 10  # finishing a fair game
XP_WIN = 5  # on top, for first place
XP_FIRST_WIN = 25  # the day's first win
XP_QUEST = 50
XP_DAILY_CAP = 400  # from games; quests come on top
QUEST_COINS = 25
LEVEL_COINS = 30

QUESTS: dict[str, dict[str, object]] = {
    "finish3": {"title": "Finish 3 games with other players", "target": 3, "social": False},
    "win1": {"title": "Win a game", "target": 1, "social": False},
    "try_game": {"title": "Play a game you've never played before", "target": 1, "social": False},
    "ranked1": {"title": "Play a ranked game", "target": 1, "social": False},
    "battle1": {"title": "Finish a battle", "target": 1, "social": False},
    "new_person": {"title": "Play with someone you've never played with", "target": 1, "social": True},
    "new_clubmate": {
        "title": "Play with a clubmate you haven't played with yet",
        "target": 1,
        "social": True,
    },
    "three_people": {"title": "Play with 3 different people today", "target": 3, "social": True},
}


def xp_for(level: int) -> int:
    """Total XP needed to reach a level (level 1 at 0, then 100, 300, 600...)."""
    return 50 * (level - 1) * level


def level_of(xp: int) -> int:
    level = max(1, int((1 + math.sqrt(1 + 8 * max(xp, 0) / 50)) / 2))
    while xp_for(level + 1) <= xp:  # guard the float maths at the edges
        level += 1
    while level > 1 and xp_for(level) > xp:
        level -= 1
    return level


# What a level-up gives besides coins: one of each game's power-ups (coins.GAME_POWER_PRICES).
LEVEL_GIFTS = (
    "trivia_fifty",
    "trivia_time",
    "drawguess_letter",
    "dice_peek",
    "chicken_shield",
    "imposter_revote",
)


def level_gift(user_id: int, level: int) -> str:
    """The power-up a level-up gives this account (the same if it's ever worked out twice)."""
    seed = int(hashlib.sha256(f"gift:{user_id}:{level}".encode()).hexdigest(), 16)
    return LEVEL_GIFTS[seed % len(LEVEL_GIFTS)]


def daily_quests(user_id: int, day: date) -> list[str]:
    """Today's three quests for this account: the same all day, different each day, one social."""
    seed = int(hashlib.sha256(f"{user_id}:{day.isoformat()}".encode()).hexdigest(), 16)
    social = sorted(q for q, info in QUESTS.items() if info["social"])
    other = sorted(q for q, info in QUESTS.items() if not info["social"])
    first = social[seed % len(social)]
    seed //= len(social)
    picks = []
    while len(picks) < 2:
        q = other[seed % len(other)]
        seed = seed // len(other) + 7
        if q not in picks:
            picks.append(q)
    return [first, *picks]
