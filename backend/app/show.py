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

    def next_game(self) -> str | None:
        """The next thing to start: a playlist game id, "jackpot", or None when the show is over."""
        if self.started < len(self.playlist):
            return self.playlist[self.started]
        if self.jackpot and not self.jackpot_played:
            return "jackpot"
        return None


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
    champ = max(totals, key=lambda p: totals[p])
    out.append(
        {
            "icon": "👑",
            "title": "Show champion",
            "text": f"{names.get(champ, '?')} with {totals[champ]} points",
        }
    )
    wins: dict[str, int] = {}
    for g in show.games:
        if g["game"] == "jackpot" or not g["scores"]:
            continue
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
    for g in show.games:
        if g["game"] == "jackpot" or len(g["scores"]) < 3:
            continue
        ordered = sorted(g["scores"].values(), reverse=True)
        for pid, pts in g["scores"].items():
            places.setdefault(pid, []).append(ordered.index(pts) + 1)
    steady = {p: sum(v) / len(v) for p, v in places.items() if len(v) >= 2}
    if steady:
        best = min(steady, key=lambda p: steady[p])
        if best != champ:
            out.append(
                {
                    "icon": "🧘",
                    "title": "Steady hand",
                    "text": f"{names.get(best, '?')} never strayed far from the top",
                }
            )
    return out
