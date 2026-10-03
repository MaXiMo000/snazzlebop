"""Price Is Weird: closest guess without going over, then the chaos spin lands.

Fairness: the hidden modifier is committed to (sha256 of "modifier:nonce") before
anyone guesses, and the nonce is revealed afterwards, so players can verify the
server did not pick the modifier after seeing the guesses.

Between items there's a quick Price Duel (two items, which costs more? +25 if right), and the
last round is the Showcase: three prizes, one bid on the total, a triple pot, Double or Nothing.
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import PRICE_ITEMS

ITEMS = PRICE_ITEMS

MODIFIERS = [0.5, 1.0, 2.0]
MODIFIER_WEIGHTS = [0.35, 0.30, 0.35]
# One mid-game round is openly "rigged": wilder multipliers (still sealed), double pot.
RIGGED_MODIFIERS = [0.1, 3.0, 5.0]
BASE_POT = 100
MAX_GUESS = 10_000_000
CHIPS_PER_GAME = 2
SHOWCASE_SIZE = 3
SHOWCASE_POT = 3  # x BASE_POT
DUEL_POINTS = 25


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
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Guess the price of a weird item. Closest WITHOUT going over wins the pot.",
        "Then a sealed chaos spin multiplies the real price (x0.5, x1 or x2): it was locked in "
        "before anyone guessed.",
        "You have two chips: sabotage a rival's guess, or double your stake.",
        "Between items: a quick duel (which costs more? +25). Last round: the Showcase, three "
        "prizes, one total, triple pot.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["reveal"])

    ROUNDS = 5

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"guess": 35.0, "reveal": 15.0, "duel": 18.0}

    def start(self) -> None:
        # Single items for rounds 1-4, a 3-prize Showcase for the last, and a pair per Price Duel.
        n_single, n_duels = self.ROUNDS - 1, self.ROUNDS - 1
        dealt = [
            ITEMS[i]
            for i in self.deal("items", len(ITEMS), n_single + SHOWCASE_SIZE + 2 * n_duels, kind="price")
        ]
        self.showcase = dealt[n_single : n_single + SHOWCASE_SIZE]
        bundle = {
            "name": "The Showcase",
            "blurb": "Three prizes, one price tag. Bid on the total.",
            "emoji": "🎁",
            "price": sum(x["price"] for x in self.showcase),
        }
        self.items = [*dealt[:n_single], bundle]
        rest = dealt[n_single + SHOWCASE_SIZE :]
        # On the rare equal-price pair, every pick counts as right (see _settle_duel).
        self.duel_items = [(rest[2 * i], rest[2 * i + 1]) for i in range(n_duels)]
        self.duel_picks: dict[str, int] = {}
        self.duel_result: dict[str, Any] | None = None
        self.duel_history: list[dict[str, Any]] = []
        self.round = 0
        self.chips = {p.id: CHIPS_PER_GAME for p in self.players}
        self.rollover = 0
        self.history: list[dict[str, Any]] = []
        self.rigged_round = self.rng.randrange(1, self.ROUNDS - 1)  # never the opener or the final
        self.sabotage_left = {p.id: 1 for p in self.players}
        self._begin_round()

    @property
    def is_rigged(self) -> bool:
        return self.round == self.rigged_round

    @property
    def is_final(self) -> bool:
        """The last item is Double or Nothing."""
        return self.round == self.ROUNDS - 1

    # -- round lifecycle ----------------------------------------------------
    def _begin_round(self) -> None:
        self.modifier = (
            self.rng.choice(RIGGED_MODIFIERS)
            if self.is_rigged
            else self.rng.choices(MODIFIERS, MODIFIER_WEIGHTS)[0]
        )
        self.nonce = f"{self.rng.getrandbits(128):032x}"
        self.commit = commitment(self.modifier, self.nonce)
        self.guesses: dict[str, list[int]] = {}
        self.order: list[str] = []
        self.chip_used: set[str] = set()
        self.sabotage: dict[str, str] = {}  # saboteur -> target, secret until the reveal
        self.doubling: set[str] = set()  # Double or Nothing opt-ins, secret until the reveal
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
        stake = BASE_POT * (SHOWCASE_POT if self.is_final else 2 if self.is_rigged else 1)
        pot = stake + self.rollover
        if best:
            top = max(best.values())
            # Tie -> whoever locked in first.
            winner = next(pid for pid in self.order if best.get(pid) == top)
            self.add_points(winner, pot)
            self.rollover = 0
            thieves = [s for s, t in self.sabotage.items() if t == winner]
            if thieves:
                share = (pot // 2) // len(thieves)
                for s in thieves:
                    self.add_points(s, share)
                self.add_points(winner, -share * len(thieves))
        else:
            self.rollover += stake
        double: dict[str, str] = {}
        if self.is_final:
            for pid in sorted(self.doubling):
                won = pid == winner
                self.round_scores[pid] = self.round_scores.get(pid, 0) * 2 if won else 0
                double[pid] = "doubled" if won else "wiped"
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
            "rigged": self.is_rigged,
            "sabotage": dict(self.sabotage),
            "double": double,
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
        elif self.phase == "reveal":
            self.duel_picks = {}
            self.phase = "duel"
            self.set_deadline(self.timings["duel"])
            self.bump()
        else:
            self._settle_duel()
            self.round += 1
            self._begin_round()

    def _settle_duel(self) -> None:
        a, b = self.duel_items[self.round]
        answer = 0 if a["price"] > b["price"] else 1 if b["price"] > a["price"] else None
        right = sorted(p for p, pick in self.duel_picks.items() if answer is None or pick == answer)
        for pid in right:
            self.add_points(pid, DUEL_POINTS)
        self.duel_result = {
            "items": [{**self._public(x), "price": x["price"]} for x in (a, b)],
            "answer": answer,
            "picks": dict(self.duel_picks),
            "right": right,
        }
        self.duel_history.append(self.duel_result)

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        return {"name": item["name"], "blurb": item["blurb"], "emoji": item["emoji"]}

    # -- actions ------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind not in ("guess", "sabotage", "double", "duel"):
            raise GameError("bad_action", "Unknown action")
        if kind == "duel":
            if self.phase != "duel":
                raise GameError("wrong_phase", "No duel right now")
            self.duel_picks[pid] = as_int(action.get("pick"), lo=0, hi=1, field="Pick")
            self.bump()
            if len(self.duel_picks) == len(self.players):
                self._next()
            return
        if self.phase != "guess":
            raise GameError("wrong_phase", "Guessing is closed")
        if kind == "sabotage":
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_input", "Pick another player to sabotage")
            if self.sabotage_left.get(pid, 0) <= 0:
                raise GameError("no_sabotage", "You've already used your sabotage token")
            self.sabotage_left[pid] -= 1
            self.sabotage[pid] = target
            self.bump()
            return
        if kind == "double":
            if not self.is_final:
                raise GameError("wrong_phase", "Double or Nothing is only on the final item")
            if pid in self.guesses:
                raise GameError("already_locked", "Decide before you lock in your guess")
            if action.get("on") is True:
                self.doubling.add(pid)
            elif action.get("on") is False:
                self.doubling.discard(pid)
            else:
                raise GameError("bad_input", "Say yes or no")
            self.bump()
            return
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
        self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "guess":
            self._resolve()
        elif self.phase in ("reveal", "duel"):
            self._next()

    # -- views --------------------------------------------------------------
    def peek(self, pid: str) -> str | None:
        """Power card: which way this round's sealed chaos spin goes."""
        if self.phase != "guess":
            return None
        if self.modifier > 1:
            return "The sealed spin will push this price UP."
        if self.modifier < 1:
            return "The sealed spin will shrink this price."
        return "The sealed spin leaves this price alone."

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
            "rigged": self.is_rigged,
            "final_round": self.is_final,
            # Only your own secret moves: nobody sees who sabotaged whom or who doubled until the reveal.
            "sabotage_left": self.sabotage_left.get(pid, 0),
            "your_sabotage": self.sabotage.get(pid) if self.phase == "guess" else None,
            "your_double": pid in self.doubling if self.phase == "guess" else False,
        }
        # The base price and modifier stay hidden until the reveal.
        if self.phase in ("reveal", "final") and self.last_result:
            view["result"] = self.last_result
        if self.phase == "guess" and pid in self.guesses:
            view["your_guesses"] = self.guesses[pid]
        if self.is_final:
            view["showcase"] = [self._public(x) for x in self.showcase]
            if self.phase in ("reveal", "final"):
                view["showcase_prices"] = [x["price"] for x in self.showcase]
        if self.phase == "duel":
            a, b = self.duel_items[self.round]
            view["duel"] = {
                "items": [self._public(a), self._public(b)],
                "locked": sorted(self.duel_picks),
                "your_pick": self.duel_picks.get(pid),
            }
        if self.phase == "guess" and self.duel_result is not None:
            view["last_duel"] = self.duel_result  # the duel that just ended
        if self.phase == "final":
            view["history"] = self.history
            view["duels"] = self.duel_history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        close = [
            (r["true_price"] - max(g for g in r["guesses"][r["winner"]] if g <= r["true_price"]), r)
            for r in self.history
            if r["winner"]
        ]
        if close:
            gap, r = min(close, key=lambda x: x[0])
            text = f"{self.name_of(r['winner'])} was ${gap:,} under on the {r['item']}"
            out.append({"icon": "🎯", "title": "Bargain hunter", "text": text})
        last = self.history[-1] if self.history else None
        if last and last["winner"]:
            text = f"{self.name_of(last['winner'])} took the Showcase pot of {last['pot']}"
            out.append({"icon": "🎁", "title": "Showcase winner", "text": text})
        if last:
            for pid, how in last["double"].items():
                icon, title = (
                    ("💥", "Double or nothing: doubled!")
                    if how == "doubled"
                    else ("🫠", "Double or nothing: wiped")
                )
                out.append({"icon": icon, "title": title, "text": f"{self.name_of(pid)} bet the lot"})
        for r in self.history:
            for saboteur, target in r["sabotage"].items():
                if r["winner"] == target:
                    text = f"{self.name_of(saboteur)} skimmed half of {self.name_of(target)}'s pot"
                    out.append({"icon": "🦹", "title": "Saboteur payday", "text": text})
        wins: dict[str, int] = {}
        for d in self.duel_history:
            for pid in d["right"]:
                wins[pid] = wins.get(pid, 0) + 1
        if wins:
            best = max(wins, key=lambda p: wins[p])
            if wins[best] == len(self.duel_history) and wins[best] >= 3:
                out.append(
                    {
                        "icon": "⚔️",
                        "title": "Duel master",
                        "text": f"{self.name_of(best)} won every price duel",
                    }
                )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
