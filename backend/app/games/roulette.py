"""Roulette Royale: friends' roulette where one of you secretly owns the house.

European wheel (0-36), six spins, 1,000 chips each. Every spin one player is secretly the House: they
don't bet; the House collects every losing stake and pays every win, so they're rooting against the
table. Everyone else places up to three bets (red/black, odd/even, low/high pay 1:1; a dozen pays 2:1;
a single number pays 35:1; zero loses every outside bet) and may name who they think the House is
(+100 if right). Score: your final stack minus the 1,000 you started with.

Fairness: the spin is drawn when betting opens and committed to (sha256 of "number:nonce"); the
nonce is revealed with the spin, so anyone can check it wasn't picked after the bets.
Secrecy: nobody learns who the House is, or anyone else's bets, until the spin. To keep the House's
cover, the House "locks in" like everyone else (with a decoy guess) and only a count is shown.
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar

from .base import Game, GameError, as_int

ROUNDS = 6
START_CHIPS = 1000
STAKES = (50, 100, 200)
MAX_BETS = 3
SPOT_BONUS = 100  # for naming the House
RED = frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36})
KINDS = {"red", "black", "odd", "even", "low", "high", "dozen", "number"}


def commitment(number: int, nonce: str) -> str:
    return hashlib.sha256(f"{number}:{nonce}".encode()).hexdigest()


def wins(kind: str, value: int | None, n: int) -> bool:
    if kind == "number":
        return n == value
    if n == 0:
        return False
    return {
        "red": n in RED,
        "black": n not in RED,
        "odd": n % 2 == 1,
        "even": n % 2 == 0,
        "low": n <= 18,
        "high": n >= 19,
        "dozen": value is not None and (n - 1) // 12 + 1 == value,
    }[kind]


def payout(kind: str) -> int:
    return 35 if kind == "number" else 2 if kind == "dozen" else 1


class RouletteRoyale(Game):
    game_id: ClassVar[str] = "roulette"
    title: ClassVar[str] = "Roulette Royale"
    blurb: ClassVar[str] = (
        "Bet on the wheel, but one of you secretly owns the house and wins whatever you lose. "
        "Spot the House for a bonus."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"bet": 35.0, "spin": 10.0}

    def start(self) -> None:
        self.chips = {p.id: START_CHIPS for p in self.players}
        self.house_count = {p.id: 0 for p in self.players}
        self.last_house: str | None = None
        self.history: list[dict[str, Any]] = []
        self.spins: list[int] = []
        self.round = 0
        self._open()

    def _pick_house(self) -> str:
        fewest = min(self.house_count.values())
        pool = [p for p in self.player_ids if self.house_count[p] == fewest and p != self.last_house]
        return self.rng.choice(pool or [p for p in self.player_ids if self.house_count[p] == fewest])

    def _open(self) -> None:
        self.house = self._pick_house()
        self.house_count[self.house] += 1
        self.number = self.rng.randrange(37)
        self.nonce = f"{self.rng.getrandbits(128):032x}"
        self.commit = commitment(self.number, self.nonce)
        self.bets: dict[str, list[dict[str, Any]]] = {}
        self.accuse: dict[str, str] = {}
        self.locked: set[str] = set()
        self.result: dict[str, Any] | None = None
        self.phase = "bet"
        self.set_deadline(self.timings["bet"])
        self.bump()

    def _parse(self, pid: str, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or len(raw) > MAX_BETS:
            raise GameError("bad_input", f"Up to {MAX_BETS} bets")
        bets: list[dict[str, Any]] = []
        for b in raw:
            if not isinstance(b, dict) or b.get("kind") not in KINDS:
                raise GameError("bad_input", "Unknown bet")
            kind = b["kind"]
            value = None
            if kind == "number":
                value = as_int(b.get("value"), lo=0, hi=36, field="Number")
            elif kind == "dozen":
                value = as_int(b.get("value"), lo=1, hi=3, field="Dozen")
            amount = as_int(b.get("amount"), lo=STAKES[0], hi=STAKES[-1], field="Stake")
            if amount not in STAKES:
                raise GameError("bad_input", "Pick one of the chip sizes")
            bets.append({"kind": kind, "value": value, "amount": amount})
        # Checked only when betting: a stack can be negative after a bad turn as the House, and that
        # player must still be able to lock in (with no bets) so the spin isn't held up.
        if bets and sum(b["amount"] for b in bets) > self.chips[pid]:
            raise GameError("bad_input", "You don't have that many chips")
        return bets

    def _spin(self) -> None:
        n = self.number
        net: dict[str, int] = {}
        for pid, bets in self.bets.items():
            total = 0
            for b in bets:
                total += b["amount"] * payout(b["kind"]) if wins(b["kind"], b["value"], n) else -b["amount"]
            net[pid] = total
            self.chips[pid] += total
        house_net = -sum(net.values())
        self.chips[self.house] += house_net
        spotted = sorted(p for p, t in self.accuse.items() if t == self.house and p != self.house)
        for pid in spotted:
            self.chips[pid] += SPOT_BONUS
        self.spins.append(n)
        self.result = {
            "number": n,
            "color": "green" if n == 0 else "red" if n in RED else "black",
            "nonce": self.nonce,
            "commit": self.commit,
            "house": self.house,
            "house_net": house_net,
            "bets": {p: [dict(b) for b in bs] for p, bs in self.bets.items()},
            "net": net,
            "accuse": {p: t for p, t in self.accuse.items() if p != self.house},
            "spotted": spotted,
        }
        self.history.append(self.result)
        self.last_house = self.house
        self.phase = "spin"
        self.set_deadline(self.timings["spin"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= ROUNDS:
            for pid in self.player_ids:
                self.round_scores[pid] = self.chips[pid] - START_CHIPS
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._open()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "lock":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "bet":
            raise GameError("wrong_phase", "No more bets")
        if pid in self.locked:
            raise GameError("already_locked", "You're locked in")
        accuse = action.get("accuse")
        if accuse is not None and (not isinstance(accuse, str) or accuse not in self.chips or accuse == pid):
            raise GameError("bad_input", "Name someone else")
        if pid == self.house:
            self._parse(pid, action.get("bets", []))  # validated like anyone's (no tell), then ignored
        else:
            self.bets[pid] = self._parse(pid, action.get("bets", []))
        if accuse is not None:
            self.accuse[pid] = accuse
        self.locked.add(pid)
        self.bump()
        if len(self.locked) == len(self.players):
            self._spin()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "bet":
            self._spin()
        elif self.phase == "spin":
            self._next()

    def view_for(self, pid: str) -> dict[str, Any]:
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "chips": dict(self.chips),
            "stakes": list(STAKES),
            "max_bets": MAX_BETS,
            "commit": self.commit,
            "locked_count": len(self.locked) if self.phase == "bet" else 0,  # a count, never who
            "spins": list(self.spins),
            "you": {
                "is_house": pid == self.house and self.phase == "bet",
                "locked": pid in self.locked,
                "bets": [dict(b) for b in self.bets.get(pid, [])],
                "accuse": self.accuse.get(pid),
            },
        }
        if self.phase in ("spin", "final") and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        straight = [
            (p, h)
            for h in self.history
            for p, bs in h["bets"].items()
            for b in bs
            if b["kind"] == "number" and b["value"] == h["number"]
        ]
        if straight:
            p, h = straight[0]
            out.append(
                {
                    "icon": "🎯",
                    "title": "Straight up!",
                    "text": f"{self.name_of(p)} called {h['number']} on the nose",
                }
            )
        best_house = max(self.history, key=lambda h: h["house_net"], default=None)
        if best_house and best_house["house_net"] > 0:
            text = f"{self.name_of(best_house['house'])} took {best_house['house_net']} as the House"
            out.append({"icon": "🏦", "title": "The house always wins", "text": text})
        spotters: dict[str, int] = {}
        for h in self.history:
            for p in h["spotted"]:
                spotters[p] = spotters.get(p, 0) + 1
        if spotters:
            sleuth = max(spotters, key=lambda p: spotters[p])
            if spotters[sleuth] >= 2:
                out.append(
                    {
                        "icon": "🕵️",
                        "title": "House detective",
                        "text": f"{self.name_of(sleuth)} spotted the House {spotters[sleuth]} times",
                    }
                )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "spins": len(self.spins)}
