"""Liar's Dice: private dice, public bids, call the bluff.

Everyone rolls their dice in secret. Taking turns, players bid on how many dice *on the whole table*
show a face ("five 4s"); ones are wild and count as any face. Each bid must raise the last: more
dice, or the same number of a higher face. Instead of bidding you can call "Liar!" (all dice are
revealed: if there are fewer than bid, the bidder loses a die, otherwise the caller does) or "Spot
on!" (exactly that many: you win a die back, up to your starting count; otherwise you lose one).
Lose all your dice and you're out; the last one rolling wins. Score: 100 per player you outlast,
+300 for the winner.

Secrecy: your dice reach only you until a challenge reveals the table, and the reveal shows that
round's dice only.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

FACES = 6
OUTLAST_POINTS = 100
WINNER_POINTS = 300


def dice_for(players: int) -> int:
    """Fewer dice at bigger tables so a game takes minutes, not an hour."""
    return 5 if players <= 3 else 4 if players <= 5 else 3


class LiarsDice(Game):
    game_id: ClassVar[str] = "dice"
    title: ClassVar[str] = "Liar's Dice"
    blurb: ClassVar[str] = (
        "Your dice are secret, your bids are not. Bid on the whole table (ones are wild), raise or "
        "call LIAR! Lose your dice and you're out."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"turn": 30.0, "reveal": 8.0}

    def start(self) -> None:
        self.start_dice = dice_for(len(self.players))
        self.counts: dict[str, int] = {p.id: self.start_dice for p in self.players}
        self.out: list[str] = []  # in the order they went out
        self.history: list[dict[str, Any]] = []
        self.opener = self.rng.choice(self.player_ids)
        self.round = 0
        self._roll()

    # -- flow ---------------------------------------------------------------
    def alive(self) -> list[str]:
        return [p for p in self.player_ids if self.counts[p] > 0]

    def _roll(self) -> None:
        self.dice: dict[str, list[int]] = {
            p: sorted(self.rng.randint(1, FACES) for _ in range(self.counts[p])) for p in self.alive()
        }
        self.bid: dict[str, Any] | None = None  # {"player", "qty", "face"}
        self.turn = self.opener if self.counts.get(self.opener, 0) > 0 else self._after(self.opener)
        self.last: dict[str, Any] | None = None
        self.phase = "bid"
        self.set_deadline(self.timings["turn"])
        self.bump()

    def _after(self, pid: str) -> str:
        order = self.player_ids
        i = order.index(pid)
        for k in range(1, len(order) + 1):
            nxt = order[(i + k) % len(order)]
            if self.counts[nxt] > 0:
                return nxt
        return pid

    def total_dice(self) -> int:
        return sum(self.counts[p] for p in self.alive())

    def count_face(self, face: int) -> int:
        return sum(1 for ds in self.dice.values() for d in ds if d == face or d == 1)

    def _challenge(self, caller: str, kind: str) -> None:
        bid = self.bid
        if bid is None:  # handle() already refuses this; kept so the type is narrowed honestly
            raise GameError("bad_input", "There's no bid to challenge yet")
        actual = self.count_face(bid["face"])
        if kind == "liar":
            loser = bid["player"] if actual < bid["qty"] else caller
            winner_back = None
        else:  # spot on
            exact = actual == bid["qty"]
            loser = None if exact else caller
            winner_back = caller if exact and self.counts[caller] < self.start_dice else None
        if loser is not None:
            self.counts[loser] -= 1
            if self.counts[loser] == 0:
                self.out.append(loser)
        if winner_back is not None:
            self.counts[winner_back] += 1
        self.last = {
            "call": kind,
            "caller": caller,
            "bid": dict(bid),
            "actual": actual,
            "loser": loser,
            "gained": winner_back,
            "dice": {p: list(ds) for p, ds in self.dice.items()},
        }
        self.history.append({k: v for k, v in self.last.items() if k != "dice"})
        # The loser opens the next round (or the caller after a spot-on, or whoever's next).
        nxt = loser if loser is not None else caller
        self.opener = nxt if self.counts.get(nxt, 0) > 0 else self._after(nxt)
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _after_reveal(self) -> None:
        if len(self.alive()) <= 1:
            self._finish()
        else:
            self.round += 1
            self._roll()

    def _finish(self) -> None:
        # Placings: the survivor first, then the knocked-out in reverse order.
        self.standings = self.alive() + list(reversed(self.out))
        n = len(self.standings)
        for place, pid in enumerate(self.standings):
            self.round_scores[pid] = OUTLAST_POINTS * (n - 1 - place) + (WINNER_POINTS if place == 0 else 0)
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- actions ------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind not in ("bid", "liar", "spot"):
            raise GameError("bad_action", "Unknown action")
        if self.phase != "bid":
            raise GameError("wrong_phase", "Wait for the next roll")
        if pid != self.turn:
            raise GameError("not_your_turn", "It's not your turn")
        if kind == "bid":
            qty = as_int(action.get("qty"), lo=1, hi=self.total_dice(), field="Number of dice")
            face = as_int(action.get("face"), lo=2, hi=FACES, field="Face")
            if self.bid and not (
                qty > self.bid["qty"] or (qty == self.bid["qty"] and face > self.bid["face"])
            ):
                raise GameError("bad_input", "Raise the bid: more dice, or the same number of a higher face")
            self.bid = {"player": pid, "qty": qty, "face": face}
            self.turn = self._after(pid)
            self.set_deadline(self.timings["turn"])
            self.bump()
            return
        if self.bid is None:
            raise GameError("bad_input", "There's no bid to challenge yet")
        self._challenge(pid, "liar" if kind == "liar" else "spot")

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        """Timer (or host skip): a silent opener bids the minimum, a silent challenger calls liar."""
        if self.finished:
            return
        if self.phase == "bid":
            if self.bid is None:
                self.bid = {"player": self.turn, "qty": 1, "face": 2}
                self.turn = self._after(self.turn)
                self.set_deadline(self.timings["turn"])
                self.bump()
            else:
                self._challenge(self.turn, "liar")
        elif self.phase == "reveal":
            self._after_reveal()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": 0,  # until one is left
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "counts": dict(self.counts),  # how many dice each player has: public
            "total": self.total_dice(),
            "start_dice": self.start_dice,
            "bid": dict(self.bid) if self.bid else None,
            "turn": self.turn if self.phase == "bid" else None,
            "you": {"dice": list(self.dice.get(pid, [])) if self.phase != "final" else []},
            "out": list(self.out),
            "history": self.history[-12:],
        }
        if self.phase in ("reveal", "final") and self.last:
            view["last"] = self.last  # the challenged round's dice, now public
        if self.phase == "final":
            view["standings"] = list(self.standings)
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = [
            {
                "icon": "🎲",
                "title": "Last one rolling",
                "text": f"{self.name_of(self.standings[0])} won Liar's Dice",
            }
        ]
        spot = [h for h in self.history if h["call"] == "spot" and h["loser"] is None]
        if spot:
            out.append(
                {
                    "icon": "🎯",
                    "title": "Spot on!",
                    "text": f"{self.name_of(spot[0]['caller'])} called it exactly",
                }
            )
        bluffs = [h for h in self.history if h["call"] == "liar" and h["loser"] == h["caller"]]
        if bluffs:
            text = f"{self.name_of(bluffs[0]['bid']['player'])} was telling the truth when it counted"
            out.append({"icon": "😇", "title": "Honest bid", "text": text})
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "challenges": len(self.history)}
