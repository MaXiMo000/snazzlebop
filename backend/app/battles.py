"""Battles: a challenge between club members, played in a room. Nobody stakes anything: the platform
pays fixed prizes from the server's final scores, through the coin ledger. Pure.

A duel is two members on a two-player game; a group battle is 3-8 members in a club room. Limits keep
prizes from being farmed: a daily number of prizes per account, and the rules in fairplay.py (the same
group of accounts, shared devices, new accounts, games that end too quickly).

Each week features one battle format (a game, or group battles in any game): a battle in it pays its
winners FEATURE_BONUS times the usual prize. A battle counts for the week it was challenged in.
"""

from __future__ import annotations

from datetime import date

DUEL_GAMES = ("four", "chess", "ships", "trivia")  # head-to-head games a challenge can name
GROUP_MIN, GROUP_MAX = 3, 8
DUEL_PRIZE = 40  # the duel's winner
GROUP_PRIZE = 60  # first place in a group battle (shared places each get it)
FINISH_PRIZE = 10  # everyone else who played to the end
DAILY_PRIZES = 10  # battle prizes an account can win in 24 hours
OPEN_HOURS = 24  # an unanswered challenge lapses
FEATURE_BONUS = 1.5  # the week's featured format pays its winners this much more
EPOCH = date(2026, 1, 5)  # a Monday: format weeks count from here

# id -> (title, what it features, games (None = any), kinds)
FORMATS: dict[str, tuple[str, str, tuple[str, ...] | None, tuple[str, ...]]] = {
    "speed": ("Speed duel week", "Four in a Row duels", ("four",), ("duel",)),
    "trivia": ("Trivia showdown", "Trivia battles, duels and groups", ("trivia",), ("duel", "group")),
    "chess": ("Grandmaster week", "Chess duels", ("chess",), ("duel",)),
    "crowd": ("Big battle week", "Group battles in any game", None, ("group",)),
    "fleet": ("Fleet week", "Battleships duels", ("ships",), ("duel",)),
}


def format_of(day: date) -> str:
    """This week's featured format (the same Monday to Sunday, the same for everyone)."""
    week = (day - EPOCH).days // 7
    return list(FORMATS)[week % len(FORMATS)]


def featured(fmt: str, kind: str, game: str) -> bool:
    _, _, games, kinds = FORMATS[fmt]
    return kind in kinds and (games is None or game in games)


def prizes(kind: str, placing: dict[int, int], finished: set[int], bonus: bool = False) -> dict[int, int]:
    """account -> coins for one battle. `placing`: account -> place (1 = best, ties share);
    only accounts in `finished` (still there at the end) win anything. `bonus`: the week's featured
    format, which raises the winners' prize."""
    top = int((DUEL_PRIZE if kind == "duel" else GROUP_PRIZE) * (FEATURE_BONUS if bonus else 1))
    out: dict[int, int] = {}
    winners = [u for u, p in placing.items() if p == 1 and u in finished]
    for uid in placing:
        if uid not in finished:
            out[uid] = 0
        elif placing[uid] == 1:
            if kind == "duel":
                # a drawn duel splits the prize, so agreeing a draw is never worth more than playing
                out[uid] = top // len(winners)
            else:
                out[uid] = top
        else:
            out[uid] = FINISH_PRIZE
    return out


def limited(won_today: int, prize: int) -> int:
    """What's actually paid once the account's daily prize count is reached."""
    return prize if won_today < DAILY_PRIZES else 0
