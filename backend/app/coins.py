"""Coins and power-ups: the rules, kept pure (no I/O) so the hub and the HTTP layer share them.

Finishing places in any game with 2+ players earn coins: 1st 50, 2nd 30, 3rd 20, 4th 10, everyone
else 5. Ties share the better place, but a game where everyone ties (nobody beat anybody, e.g. two
accounts skipping through a game at 0-0) pays nothing. At most DAILY_COIN_CAP coins a day per account
(a brake on farming with spare accounts). Coins buy power-ups: the show's power cards, one per game.
"""

from __future__ import annotations

from datetime import UTC, datetime

PLACE_COINS = (50, 30, 20, 10)
EVERYONE_ELSE = 5
DAILY_COIN_CAP = 600
POWERUP_PRICES = {"peek": 40, "shield": 60, "steal": 60, "double": 80}  # the show's cards (no longer sold)
# Each game's own power-ups (games/*.py POWERS), sold in the shop for coins.
GAME_POWER_PRICES = {
    "trivia_fifty": 30,
    "trivia_time": 20,
    "drawguess_letter": 30,
    "dice_peek": 40,
    "chicken_shield": 50,
    "imposter_revote": 30,
    "four_undo": 30,
    "rather_room": 25,
    "ships_sonar": 40,
    "hangman_vowel": 25,
    "tod_fresh": 20,
    "wordrace_letter": 30,
    "codes_peek": 30,
    "lastcard_peek": 25,
    "snakes_repel": 25,
    "fivedice_roll": 30,
}
# Emote packs (party.py): bought once, kept for good.
EMOTE_PRICES = {
    pack: 40 for pack in ("emote_spooky", "emote_animals", "emote_snacks", "emote_royal", "emote_weather")
}
# Party items (party.py): no effect on scores, used anywhere in a room.
PARTY_PRICES = {
    "party_confetti": 15,
    "party_airhorn": 15,
    "party_drumroll": 20,
    "party_ovation": 20,
    "party_spotlight": 25,
    "party_replay": 25,
}


def places(scores: dict[str, int]) -> dict[str, int]:
    """1-based finishing places; ties share the better place (two on 300 are both 1st, next is 3rd)."""
    order = sorted(scores.values(), reverse=True)
    return {pid: order.index(v) + 1 for pid, v in scores.items()}


def coins_for(place: int, players: int, *, all_tied: bool = False) -> int:
    if players < 2 or all_tied:
        return 0
    return PLACE_COINS[place - 1] if place <= len(PLACE_COINS) else EVERYONE_ELSE


def season_of(when: datetime | None = None) -> str:
    """Seasons are calendar months (UTC): "2026-10"."""
    return (when or datetime.now(UTC)).strftime("%Y-%m")
