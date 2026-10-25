"""Battles: a challenge between club members, played in a room. Nobody stakes anything: the platform
pays fixed prizes from the server's final scores, through the coin ledger. Pure.

A duel is two members on a two-player game; a group battle is 3-8 members in a club room. Limits keep
prizes from being farmed: a daily number of prizes per account, and the rules in fairplay.py (the same
group of accounts, shared devices, new accounts, games that end too quickly).
"""

from __future__ import annotations

DUEL_GAMES = ("four", "chess", "ships", "trivia")  # head-to-head games a challenge can name
GROUP_MIN, GROUP_MAX = 3, 8
DUEL_PRIZE = 40  # the duel's winner
GROUP_PRIZE = 60  # first place in a group battle (shared places each get it)
FINISH_PRIZE = 10  # everyone else who played to the end
DAILY_PRIZES = 10  # battle prizes an account can win in 24 hours
OPEN_HOURS = 24  # an unanswered challenge lapses


def prizes(kind: str, placing: dict[int, int], finished: set[int]) -> dict[int, int]:
    """account -> coins for one battle. `placing`: account -> place (1 = best, ties share);
    only accounts in `finished` (still there at the end) win anything."""
    out: dict[int, int] = {}
    winners = [u for u, p in placing.items() if p == 1 and u in finished]
    for uid in placing:
        if uid not in finished:
            out[uid] = 0
        elif placing[uid] == 1:
            if kind == "duel":
                # a drawn duel splits the prize, so agreeing a draw is never worth more than playing
                out[uid] = DUEL_PRIZE // len(winners)
            else:
                out[uid] = GROUP_PRIZE
        else:
            out[uid] = FINISH_PRIZE
    return out


def limited(won_today: int, prize: int) -> int:
    """What's actually paid once the account's daily prize count is reached."""
    return prize if won_today < DAILY_PRIZES else 0
