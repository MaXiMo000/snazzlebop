"""Price Is Weird: closest guess without going over, then the chaos spin lands.

Fairness: the hidden modifier is committed to (sha256 of "modifier:nonce") before
anyone guesses, and the nonce is revealed afterwards, so players can verify the
server did not pick the modifier after seeing the guesses.
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import PRICE_ITEMS

ITEMS = PRICE_ITEMS

MODIFIERS = [0.5, 1.0, 2.0]
MODIFIER_WEIGHTS = [0.35, 0.30, 0.35]
BASE_POT = 100
MAX_GUESS = 10_000_000
CHIPS_PER_GAME = 2


def commitment(modifier: float, nonce: str) -> str:
    return hashlib.sha256(f"{modifier}:{nonce}".encode()).hexdigest()


class PriceIsWeird(Game):
    game_id: ClassVar[str] = "price"
    title: ClassVar[str] = "Price Is Weird"
    blurb: ClassVar[str] = (
        "Guess the price of something absurd. Closest without going over wins "
        "- unless the chaos spin doubles or halves it."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    ROUNDS = 5

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"guess": 25.0, "reveal": 10.0}

    def start(self) -> None:
        self.items = [ITEMS[i] for i in self.deal("items", len(ITEMS), self.ROUNDS)]
        self.round = 0
        self.chips = {p.id: CHIPS_PER_GAME for p in self.players}
        self.rollover = 0
        self.history: list[dict[str, Any]] = []
        self._begin_round()

    # -- round lifecycle ----------------------------------------------------
    def _begin_round(self) -> None:
        self.modifier = self.rng.choices(MODIFIERS, MODIFIER_WEIGHTS)[0]
        self.nonce = f"{self.rng.getrandbits(128):032x}"
        self.commit = commitment(self.modifier, self.nonce)
        self.guesses: dict[str, list[int]] = {}
        self.order: list[str] = []
        self.chip_used: set[str] = set()
        self.last_result: dict[str, Any] | None = None
        self.phase = "guess"
        self.set_deadline(self.timings["guess"])
        self.bump()

    def _resolve(self) -> None:
        item = self.items[self.round]
        true_price = int(round(item["price"] * self.modifier))
        best: dict[str, int] = {}
        for pid, gs in self.guesses.items():
            valid = [g for g in gs if g <= true_price]
            if valid:
                best[pid] = max(valid)
        winner: str | None = None
        pot = BASE_POT + self.rollover
        if best:
            top = max(best.values())
            # Tie -> whoever locked in first.
            winner = next(pid for pid in self.order if best.get(pid) == top)
            self.add_points(winner, pot)
            self.rollover = 0
        else:
            self.rollover += BASE_POT
        self.last_result = {
            "item": item["name"],
            "base_price": item["price"],
            "modifier": self.modifier,
            "true_price": true_price,
            "nonce": self.nonce,
            "commit": self.commit,
            "guesses": {pid: gs for pid, gs in self.guesses.items()},
            "winner": winner,
            "pot": pot if winner else 0,
            "rollover": self.rollover,
        }
        self.history.append(self.last_result)
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= self.ROUNDS:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._begin_round()

    # -- actions ------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "guess":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "guess":
            raise GameError("wrong_phase", "Guessing is closed")
        if pid in self.guesses:
            raise GameError("already_locked", "Your guess is already locked in")
        amount = as_int(action.get("amount"), lo=1, hi=MAX_GUESS, field="Guess")
        guesses = [amount]
        if action.get("amount2") is not None:
            if self.chips[pid] <= 0:
                raise GameError("no_chips", "No hedge chips left")
            guesses.append(as_int(action["amount2"], lo=1, hi=MAX_GUESS, field="Second guess"))
            self.chips[pid] -= 1
            self.chip_used.add(pid)
        self.guesses[pid] = guesses
        self.order.append(pid)
        self.bump()
        if len(self.guesses) == len(self.players):
            self._resolve()

    def tick(self) -> None:
        if self.finished or not self.expired():
            return
        if self.phase == "guess":
            self._resolve()
        elif self.phase == "reveal":
            self._next()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "guess":
            self._resolve()
        elif self.phase == "reveal":
            self._next()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        item = self.items[self.round]
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.ROUNDS,
            "remaining": self.remaining(),
            "item": {"name": item["name"], "blurb": item["blurb"], "emoji": item["emoji"]},
            "commit": self.commit,
            "chips": self.chips.get(pid, 0),
            "locked": sorted(self.guesses),
            "you_locked": pid in self.guesses,
            "rollover": self.rollover,
        }
        # The base price and modifier stay hidden until the reveal.
        if self.phase in ("reveal", "final") and self.last_result:
            view["result"] = self.last_result
        if self.phase == "guess" and pid in self.guesses:
            view["your_guesses"] = self.guesses[pid]
        if self.phase == "final":
            view["history"] = self.history
        return view

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
