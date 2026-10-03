"""Jackpot Round: the finale of a show night.

One absurd item and a price tag that's wrong on purpose. Everyone secretly wagers some of their show
score on whether the real price is higher or lower. Right doubles the stake back, wrong loses it.
Wagers and calls stay hidden (even from the TV) until the reveal, which is also the end of the game.

Not in the lobby catalog: the hub starts it after the last game of a show that has the jackpot on.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, Player, as_int
from .content import PRICE_ITEMS

FLOOR = 200  # everyone can wager at least this much, so players at the bottom still have a shot
CALLS = ("higher", "lower")


class Jackpot(Game):
    game_id: ClassVar[str] = "jackpot"
    title: ClassVar[str] = "Jackpot Round"
    blurb: ClassVar[str] = "Wager your show score: is the real price higher or lower?"
    min_players: ClassVar[int] = 1
    max_players: ClassVar[int] = 8
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "The finale. One weird item with a price tag that's wrong on purpose.",
        "Secretly wager some of your show score: is the real price HIGHER or LOWER than the tag?",
        "Right: win your wager. Wrong: lose it. Everyone can bet at least 200.",
    )

    def __init__(
        self,
        players: list[Player],
        *args: Any,
        stakes: dict[str, int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(players, *args, **kwargs)
        stakes = stakes or {}
        self.stakes = {p.id: stakes.get(p.id, 0) for p in players}

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"wager": 45.0}

    def cap(self, pid: str) -> int:
        return max(self.stakes.get(pid, 0), FLOOR)

    def start(self) -> None:
        # Shares the Price deck: the finale never shows an item this room already priced.
        i = self.deal("items", len(PRICE_ITEMS), 1, kind="price", deck="price:items")[0]
        self.item = PRICE_ITEMS[i]
        price = self.item["price"]
        # Half the time the tag undersells the item (answer "higher"), half the time it oversells it.
        undersell = self.rng.random() < 0.5
        factor = self.rng.uniform(0.45, 0.8) if undersell else self.rng.uniform(1.25, 2.2)
        self.tag = max(1, round(price * factor))
        if self.tag == price:  # tiny prices can round onto the answer; nudge so there is one
            self.tag = price + 1
        self.answer = "higher" if price > self.tag else "lower"
        self.wagers: dict[str, dict[str, Any]] = {}
        self.result: dict[str, Any] | None = None
        self.round = 1
        self.phase = "wager"
        self.set_deadline(self.timings["wager"])
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if self.phase != "wager":
            raise GameError("wrong_phase", "Wagers are closed")
        if action.get("a") != "wager":
            raise GameError("bad_action", "Unknown action")
        amount = as_int(action.get("amount"), lo=0, hi=self.cap(pid), field="wager")
        call = action.get("call")
        if call not in CALLS:
            raise GameError("bad_input", "Call higher or lower")
        self.wagers[pid] = {"amount": amount, "call": call}
        self.bump()
        if len(self.wagers) == len(self.players):
            self._reveal()

    def _reveal(self) -> None:
        deltas: dict[str, int] = {}
        for p in self.players:
            w = self.wagers.get(p.id)
            if w is None or w["amount"] == 0:
                deltas[p.id] = 0
            else:
                deltas[p.id] = w["amount"] if w["call"] == self.answer else -w["amount"]
            self.add_points(p.id, deltas[p.id])
        self.result = {
            "price": self.item["price"],
            "answer": self.answer,
            "wagers": {pid: dict(w) for pid, w in self.wagers.items()},
            "deltas": deltas,
        }
        self.phase = "final"
        self.finished = True
        self.set_deadline(None)
        self.bump()

    def tick(self) -> None:
        if self.phase == "wager" and self.expired():
            self._reveal()

    def advance(self) -> None:
        if self.phase == "wager":
            self._reveal()

    def view_for(self, pid: str) -> dict[str, Any]:
        mine = self.wagers.get(pid)
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": 1,
            "rounds": 1,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "item": {"name": self.item["name"], "blurb": self.item["blurb"], "emoji": self.item["emoji"]},
            "tag": self.tag,
            "stakes": dict(self.stakes),
            "cap": self.cap(pid) if pid in self.stakes else 0,
            "locked": sorted(self.wagers),  # who has wagered, never what
            "you": dict(mine) if mine else None,
            "result": self.result,
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.result:
            return []
        out: list[dict[str, str]] = []
        deltas = self.result["deltas"]
        best = max(deltas, key=lambda p: deltas[p])
        worst = min(deltas, key=lambda p: deltas[p])
        if deltas[best] > 0:
            out.append(
                {
                    "icon": "💰",
                    "title": "Jackpot!",
                    "text": f"{self.name_of(best)} won {deltas[best]} on the final call",
                }
            )
        if deltas[worst] < 0:
            all_in = -deltas[worst] >= self.cap(worst)
            out.append(
                {
                    "icon": "🎢",
                    "title": "All in, all gone" if all_in else "Ouch",
                    "text": f"{self.name_of(worst)} bet {-deltas[worst]} and lost it",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "answer": self.answer}
