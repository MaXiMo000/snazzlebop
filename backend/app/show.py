"""Show night: a playlist of games on one scoreboard, an optional jackpot finale, the highlight reel and
the host's one-liners. Pure helpers (no I/O, injected rng) so the hub stays small and this stays tested.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .games.base import Deck
from .games.content import QUIP_FIELDS, QUIPS

MIN_GAMES, MAX_GAMES = 2, 6


@dataclass
class Show:
    playlist: list[str]  # game ids, in order
    jackpot: bool  # finish with the Jackpot Round
    started: int = 0  # how many playlist games have been started
    jackpot_played: bool = False
    finished: bool = False
    # One entry per finished game: {"game", "title", "scores": {pid: pts}}
    games: list[dict[str, Any]] = field(default_factory=list)
    reel: list[dict[str, str]] = field(default_factory=list)  # highlights, each tagged with its game
    awards: list[dict[str, str]] = field(default_factory=list)
    quip: str = ""
    market: Market | None = None  # Friend Stock Exchange, when the host turned it on
    # Power cards: one per player per show. Hand and plays are secret until the game's results.
    cards: dict[str, str] = field(default_factory=dict)  # pid -> card id still in hand
    plays: list[dict[str, Any]] = field(default_factory=list)  # {"pid", "card", "game", "target"?}
    peeks: dict[str, str] = field(default_factory=dict)  # pid -> what their Peek showed (private)

    def next_game(self) -> str | None:
        """The next thing to start: a playlist game id, "jackpot", or None when the show is over."""
        if self.started < len(self.playlist):
            return self.playlist[self.started]
        if self.jackpot and not self.jackpot_played:
            return "jackpot"
        return None


# -- power cards -----------------------------------------------------------------------------------
CARDS: dict[str, dict[str, str]] = {
    "double": {"name": "Double Down", "icon": "🎲", "text": "Double your points this game (losses too)"},
    "shield": {"name": "Shield", "icon": "🛡️", "text": "A losing game counts as zero"},
    "steal": {"name": "Steal 50", "icon": "🦝", "text": "Take 50 points from a rival"},
    "peek": {"name": "Peek", "icon": "👁️", "text": "See one secret in the game being played"},
}
STEAL_POINTS = 50
EARLY_CARDS = ("double", "shield")  # only before the first round of a game is over


def deal_cards(show: Show, pids: list[str], rng: random.Random) -> None:
    """One random card for everyone who doesn't have one yet (and hasn't played one this show)."""
    used = {p["pid"] for p in show.plays}
    for pid in pids:
        if pid not in show.cards and pid not in used:
            show.cards[pid] = rng.choice(sorted(CARDS))


def apply_cards(
    plays: list[dict[str, Any]], scores: dict[str, int]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """A finished game's scores after the cards played in it, and what each card did (for the reveal).
    Double first, then Shield (a doubled loss is still shielded), then steals."""
    out = dict(scores)
    news: list[dict[str, Any]] = []
    for kind in ("double", "shield", "steal", "peek"):
        for play in (p for p in plays if p["card"] == kind):
            pid, effect = play["pid"], 0
            if kind == "double" and pid in out:
                effect = out[pid]
                out[pid] += effect
            elif kind == "shield" and pid in out and out[pid] < 0:
                effect = -out[pid]
                out[pid] = 0
            elif kind == "steal":
                target = play["target"]
                out[pid] = out.get(pid, 0) + STEAL_POINTS
                out[target] = out.get(target, 0) - STEAL_POINTS
                effect = STEAL_POINTS
            news.append({**play, "effect": effect})
    return out, news


# -- rivals ----------------------------------------------------------------------------------------
RIVAL_BONUS = 50


def rivals(totals: dict[str, int], pids: list[str], rng: random.Random) -> list[tuple[str, str]]:
    """Pair everyone with the closest score on the show's board (random among ties); an odd one out
    has no rival this game."""
    order = list(pids)
    rng.shuffle(order)  # ties break randomly, then a stable sort keeps that
    order.sort(key=lambda p: -totals.get(p, 0))
    return [(order[i], order[i + 1]) for i in range(0, len(order) - 1, 2)]


def settle_rivals(pairs: list[tuple[str, str]], scores: dict[str, int]) -> list[dict[str, Any]]:
    """Who beat their rival this game (a draw pays nobody)."""
    out = []
    for a, b in pairs:
        sa, sb = scores.get(a, 0), scores.get(b, 0)
        out.append({"players": [a, b], "winner": a if sa > sb else b if sb > sa else None})
    return out


# -- the host's one-liners --------------------------------------------------------------------------
def fill(template: str, facts: dict[str, str]) -> str:
    """Plain replacement of known placeholders only. Never str.format: templates are generated text."""
    out = template
    for name in QUIP_FIELDS:
        out = out.replace("{" + name + "}", facts.get(name, ""))
    return out


def _mood(ranked: list[tuple[str, int]], final: str | None) -> str:
    if final:
        return final
    if len(ranked) < 2:
        return "win"
    (_, top), (_, second) = ranked[0], ranked[1]
    if top == second:
        return "tie"
    margin, scale = top - second, max(abs(top), 1)
    if margin <= max(20, scale // 10):
        return "close"
    if margin >= 100 and margin >= scale // 2:
        return "blowout"
    return "win"


def quip(
    scores: dict[str, int],
    names: dict[str, str],
    game_title: str,
    decks: dict[str, Deck],
    rng: random.Random,
    final: str | None = None,
) -> str:
    """One host line about a finished game (or, with final="jackpot"/"show", the finale).

    Only templates whose placeholders can all be filled are used: no {runner} in a solo game, no {last}
    unless there are three or more players. Each mood deals from the room's own no-repeat deck."""
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return ""
    if final is None and len(ranked) >= 3 and ranked[0][1] == ranked[-1][1]:
        # Everyone level: a "tie at the top" line would wrongly single out two people.
        return f"A dead heat on {game_title}: everyone finished on {ranked[0][1]}."
    if final == "show" and len(ranked) >= 2 and ranked[0][1] == ranked[1][1]:
        joint = [names.get(p, "?") for p, s in ranked if s == ranked[0][1]]
        return f"We can't split them: {' and '.join(joint)} share tonight's crown!"
    mood = _mood(ranked, final)
    facts = {"winner": names.get(ranked[0][0], "?"), "game": game_title}
    if len(ranked) >= 2:
        facts["runner"] = names.get(ranked[1][0], "?")
        facts["margin"] = str(ranked[0][1] - ranked[1][1])
    if len(ranked) >= 3:
        facts["last"] = names.get(ranked[-1][0], "?")
    usable = [
        q["text"]
        for q in QUIPS
        if q["mood"] == mood and all("{" + f + "}" not in q["text"] for f in QUIP_FIELDS if f not in facts)
    ]
    if not usable:
        return ""
    key = f"quip:{mood}:{','.join(sorted(facts))}"  # the usable list only grows for a given key
    deck = decks.get(key)
    if deck is None or deck.size > len(usable):
        deck = decks[key] = Deck(len(usable), rng)
    deck.grow(len(usable))
    return fill(usable[deck.draw(1)[0]], facts)


# -- the finale ------------------------------------------------------------------------------------
def awards(show: Show, totals: dict[str, int], names: dict[str, str]) -> list[dict[str, str]]:
    """Show-wide awards for the finale screen (game-by-game moments are in the reel)."""
    out: list[dict[str, str]] = []
    if not totals:
        return out
    ranked = sorted(totals, key=lambda p: -totals[p])
    champ = ranked[0]
    joint = [p for p in ranked if totals[p] == totals[champ]]
    out.append(
        {
            "icon": "👑",
            "title": "Show champion" if len(joint) == 1 else "Joint champions",
            "text": f"{' & '.join(names.get(p, '?') for p in joint)} with {totals[champ]} points",
        }
    )
    # Only games that actually separated people count: a 0-0 draw crowns nobody.
    decided = [
        g
        for g in show.games
        if g["game"] != "jackpot" and g["scores"] and max(g["scores"].values()) > min(g["scores"].values())
    ]
    wins: dict[str, int] = {}
    for g in decided:
        top = max(g["scores"].values())
        for pid, pts in g["scores"].items():
            if pts == top:
                wins[pid] = wins.get(pid, 0) + 1
    if wins:
        best = max(wins, key=lambda p: wins[p])
        if wins[best] >= 2:
            out.append(
                {
                    "icon": "🏆",
                    "title": "Segment king",
                    "text": f"{names.get(best, '?')} won {wins[best]} games tonight",
                }
            )
    # Most consistent: best average finishing position across the games they played.
    places: dict[str, list[int]] = {}
    for g in decided:
        if len(g["scores"]) < 3:
            continue
        ordered = sorted(g["scores"].values(), reverse=True)
        for pid, pts in g["scores"].items():
            places.setdefault(pid, []).append(ordered.index(pts) + 1)
    # The champion already has a crown; this goes to someone else who stayed near the top all night.
    steady = {
        p: sum(v) / len(v)
        for p, v in places.items()
        if len(v) >= 2 and p not in joint and p in totals and ranked.index(p) < len(ranked) / 2
    }
    if steady:
        best = min(steady, key=lambda p: steady[p])
        out.append(
            {
                "icon": "🧘",
                "title": "Steady hand",
                "text": f"{names.get(best, '?')} never strayed far from the top",
            }
        )
    return out


# -- Friend Stock Exchange ---------------------------------------------------------------------------
START_CASH = 1000
START_PRICE = 100
MIN_PRICE = 10
MAX_HOLDING = 20  # shares of any one player, long or short
MAX_TRADE = 10  # shares per trade
TOP_MOVE, BOTTOM_MOVE = 0.30, -0.20  # winner's price change ... last place's
POINTS_PER_DOLLARS = 10  # every $10 of profit (or loss) is one show point at the finale
DIVIDEND = 10  # per share of each game's winner (a short pays it)


@dataclass
class Market:
    """Shares in your friends. Cash and holdings are private; prices are public. Players are both traders
    and stocks; the audience only trades. A negative holding is a short."""

    cash: dict[str, int] = field(default_factory=dict)
    holdings: dict[str, dict[str, int]] = field(default_factory=dict)  # trader -> player -> shares
    prices: dict[str, int] = field(default_factory=dict)
    history: list[dict[str, int]] = field(default_factory=list)  # prices after each game
    trades: int = 0

    def seat(self, pid: str, *, listed: bool = True) -> None:
        self.cash.setdefault(pid, START_CASH)
        self.holdings.setdefault(pid, {})
        if listed:
            self.prices.setdefault(pid, START_PRICE)

    def trade(self, trader: str, target: str, qty: int) -> None:
        """Buy (qty > 0) or sell (qty < 0) shares of `target` at today's price. Selling more than you own
        opens a short (cash now, owe the price later). Raises ValueError."""
        if target not in self.prices or trader not in self.cash:
            raise ValueError("Unknown player")
        if qty == 0 or abs(qty) > MAX_TRADE:
            raise ValueError(f"Trade 1-{MAX_TRADE} shares at a time")
        held = self.holdings[trader].get(target, 0)
        cost = self.prices[target] * qty
        if qty > 0 and cost > self.cash[trader]:
            raise ValueError("Not enough cash")
        if held + qty > MAX_HOLDING:
            raise ValueError(f"At most {MAX_HOLDING} shares of one player")
        if held + qty < 0 and target == trader:
            raise ValueError("You can't short yourself")
        if held + qty < -MAX_HOLDING:
            raise ValueError(f"Short at most {MAX_HOLDING} shares of one player")
        self.cash[trader] -= cost
        self.holdings[trader][target] = held + qty
        if self.holdings[trader][target] == 0:
            del self.holdings[trader][target]
        self.trades += 1

    def reprice(self, scores: dict[str, int]) -> dict[str, float]:
        """After a game: the winner's price rises 30%, last place's falls 20%, linear in between (ties share
        the average of their places). Players who weren't in the game don't move."""
        ranked = sorted(scores, key=lambda p: -scores[p])
        n = len(ranked)
        moves: dict[str, float] = {}
        for pid in ranked:
            places = [i for i, q in enumerate(ranked) if scores[q] == scores[pid]]
            place = sum(places) / len(places)
            move = TOP_MOVE if n == 1 else TOP_MOVE + (BOTTOM_MOVE - TOP_MOVE) * place / (n - 1)
            if pid in self.prices:
                self.prices[pid] = max(MIN_PRICE, round(self.prices[pid] * (1 + move)))
                moves[pid] = round(move, 3)
        self.history.append(dict(self.prices))
        return moves

    def pay_dividends(self, winners: list[str]) -> dict[str, int]:
        """Each game's winner(s) pay every shareholder; shorts pay it instead. Returns cash moved."""
        paid: dict[str, int] = {}
        for trader, book in self.holdings.items():
            amount = sum(book.get(w, 0) * DIVIDEND for w in winners)
            if amount:
                self.cash[trader] += amount
                paid[trader] = amount
        return paid

    def tip(self, insider: str, rng: random.Random, names: dict[str, str]) -> str:
        """An insider tip: one other trader's whole book (books are otherwise secret)."""
        others = [t for t in self.holdings if t != insider and t in names]
        if not others:
            return ""
        who = rng.choice(sorted(others))
        book = self.holdings[who]
        if not book:
            return f"{names[who]} hasn't bought anything yet."
        parts = [f"{q:+} × {names.get(t, '?')}" for t, q in sorted(book.items(), key=lambda kv: -abs(kv[1]))]
        return f"{names[who]} holds {', '.join(parts)}."

    def worth(self, pid: str) -> int:
        return self.cash.get(pid, 0) + sum(
            q * self.prices.get(t, 0) for t, q in self.holdings.get(pid, {}).items()
        )

    def bonus(self, pid: str) -> int:
        return int((self.worth(pid) - START_CASH) / POINTS_PER_DOLLARS)
