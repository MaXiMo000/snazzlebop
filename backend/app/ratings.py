"""Skill ratings: the Weng-Lin Plackett-Luce model (as in OpenSkill), seasons and tiers. Pure.

Every player has a mean (mu) and an uncertainty (sigma) per ranked game. One update handles duels,
free-for-alls and ties the same way: players are ranked by the server's final scores (higher is
better, equal scores tie). The shown number is the cautious estimate, mu - 3 sigma, scaled so a new
player starts at 1,000.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

MU = 25.0
SIGMA = MU / 3
BETA = SIGMA / 2
KAPPA = 0.0001
TAU = MU / 300  # a little uncertainty added before each game, so ratings keep moving
SCALE = 40  # display points per unit of mu - 3 sigma

PROVISIONAL_GAMES = 5  # placement games before a number is shown
DAY_CAP = 150  # the most display points a rating can move in a day, up or down
PAIR_LIMIT = 5  # duels between the same two accounts in a day that still count

TIERS = (("Bronze", 0), ("Silver", 1100), ("Gold", 1300), ("Platinum", 1500), ("Diamond", 1700))

SEASON_WEEKS = 8
SEASON_EPOCH = date(2026, 1, 5)  # a Monday: season 1 starts here


@dataclass(frozen=True)
class Rating:
    mu: float = MU
    sigma: float = SIGMA

    @property
    def display(self) -> int:
        return max(0, round(1000 + SCALE * (self.mu - 3 * self.sigma)))


def ranks(scores: dict[str, int]) -> dict[str, int]:
    """1 for the top score; equal scores share a rank."""
    order = sorted(set(scores.values()), reverse=True)
    return {p: order.index(v) + 1 for p, v in scores.items()}


def rate(players: dict[str, Rating], rank: dict[str, int]) -> dict[str, Rating]:
    """New ratings after one game. `rank`: 1 = best, ties share a number."""
    ids = list(players)
    if len(ids) < 2:
        return dict(players)
    before = {p: Rating(players[p].mu, math.sqrt(players[p].sigma ** 2 + TAU**2)) for p in ids}
    c = math.sqrt(sum(r.sigma**2 + BETA**2 for r in before.values()))
    strength = {p: math.exp(before[p].mu / c) for p in ids}
    # sum over everyone ranked at or below q; how many share q's rank
    below = {q: sum(strength[i] for i in ids if rank[i] >= rank[q]) for q in ids}
    tied = {q: sum(1 for i in ids if rank[i] == rank[q]) for q in ids}
    out: dict[str, Rating] = {}
    for i in ids:
        omega = delta = 0.0
        for q in ids:
            if rank[q] > rank[i]:
                continue
            share = strength[i] / below[q]
            omega += ((1 - share) if q == i else -share) / tied[q]
            delta += share * (1 - share) / tied[q]
        var = before[i].sigma ** 2
        gamma = math.sqrt(var) / c
        mu = before[i].mu + var / c * omega
        sigma = before[i].sigma * math.sqrt(max(1 - var / c**2 * gamma * delta, KAPPA))
        out[i] = Rating(mu, sigma)
    return out


def capped(old: Rating, new: Rating, moved_today: int) -> Rating:
    """Keep a day's total change within DAY_CAP display points by holding back the mean."""
    room_up, room_down = DAY_CAP - moved_today, -DAY_CAP - moved_today
    change = new.display - old.display
    allowed = max(room_down, min(room_up, change))
    if allowed == change:
        return new
    target = old.display + allowed
    return Rating((target - 1000) / SCALE + 3 * new.sigma, new.sigma)


def tier(display: int, games: int) -> str:
    if games < PROVISIONAL_GAMES:
        return "Provisional"
    return [name for name, floor in TIERS if display >= floor][-1]


# -- seasons: 8 weeks each; a new season pulls every rating halfway back to the start --------------
def season_of(when: datetime | None = None) -> int:
    day = (when or datetime.now(UTC)).date()
    return max(1, (day - SEASON_EPOCH).days // (7 * SEASON_WEEKS) + 1)


def season_dates(season: int) -> tuple[date, date]:
    start = SEASON_EPOCH + timedelta(weeks=SEASON_WEEKS * (season - 1))
    return start, start + timedelta(weeks=SEASON_WEEKS, days=-1)


def soft_reset(r: Rating, seasons_passed: int) -> Rating:
    for _ in range(max(0, seasons_passed)):
        r = Rating((r.mu + MU) / 2, (r.sigma + SIGMA) / 2)
    return r


# Coins for the tier a rating ended its season on (paid once, when the next season begins for it).
SEASON_REWARD = {"Bronze": 20, "Silver": 40, "Gold": 80, "Platinum": 120, "Diamond": 200}
