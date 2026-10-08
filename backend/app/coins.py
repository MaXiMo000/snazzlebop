"""Coins and power-ups: the rules, kept pure (no I/O) so the hub and the HTTP layer share them.

Finishing places in any game with 2+ players earn coins: 1st 50, 2nd 30, 3rd 20, 4th 10, everyone
else 5. Ties share the better place. At most DAILY_COIN_CAP coins a day per account (a brake on
farming with spare accounts). Coins buy power-ups: the show's power cards, one per game.
"""

from __future__ import annotations

from datetime import UTC, datetime

PLACE_COINS = (50, 30, 20, 10)
EVERYONE_ELSE = 5
DAILY_COIN_CAP = 600
POWERUP_PRICES = {"peek": 40, "shield": 60, "steal": 60, "double": 80}


def places(scores: dict[str, int]) -> dict[str, int]:
    """1-based finishing places; ties share the better place (two on 300 are both 1st, next is 3rd)."""
    order = sorted(scores.values(), reverse=True)
    return {pid: order.index(v) + 1 for pid, v in scores.items()}


def coins_for(place: int, players: int) -> int:
    if players < 2:
        return 0
    return PLACE_COINS[place - 1] if place <= len(PLACE_COINS) else EVERYONE_ELSE


def season_of(when: datetime | None = None) -> str:
    """Seasons are calendar months (UTC): "2026-10"."""
    return (when or datetime.now(UTC)).strftime("%Y-%m")
