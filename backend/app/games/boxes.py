"""Mystery Box Auction: six sealed boxes go under the hammer, one at a time. Some hold prizes, one is
empty, and two are bombs. Before the bidding everyone secretly peeks inside one box, so every auction
has someone who knows, and nobody knows who. Bid it up, bluff with a canned claim, or let a friend
"win" the bomb.

Live auction with a soft close: every bid pushes the hammer back a few seconds. The winner pays their
bid from a coin purse (public) and scores the box's value minus the price; a bomb costs points.
Contents stay on the server until each box is sold; your peek is only in your own view.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

BOX_COUNT = 6
START_COINS = 600
MIN_BID = 10
STEP = 10
LABELS = ("A", "B", "C", "D", "E", "F")
PRIZES = (
    ("💎", "A diamond the size of a grape", 700),
    ("🏍️", "A slightly used jet ski", 600),
    ("🎟️", "Lifetime pass to a waterpark", 450),
    ("⌚", "A gold watch (it's fake, but heavy)", 300),
    ("🍕", "A year of free pizza", 400),
    ("🎸", "A guitar signed by somebody", 350),
    ("🛋️", "A massage chair", 500),
    ("🧳", "A weekend away (camping)", 250),
    ("🎮", "Every console ever made", 550),
    ("🐐", "A goat. It's yours now", 200),
    ("🍫", "A lifetime of chocolate", 300),
    ("🪙", "A sack of old coins", 650),
)
BOMBS = (
    ("💣", "BOOM. A bomb.", -300),
    ("🧨", "A box of fireworks. Lit.", -200),
    ("🦨", "A very angry skunk", -250),
    ("🧾", "Someone else's tax bill", -400),
    ("🐝", "Bees. Just bees.", -150),
    ("📼", "Your worst karaoke, on tape, playing", -200),
)
DUD = ("🫥", "Absolutely nothing", 0)
CLAIMS = (
    "This one's a winner 🤑",
    "It's a bomb, back off 💣",
    "Empty. Trust me 🫥",
    "I didn't see this one 🤷",
    "I'd pay anything for it 😍",
)


class MysteryBoxes(Game):
    game_id: ClassVar[str] = "boxes"
    title: ClassVar[str] = "Mystery Box Auction"
    blurb: ClassVar[str] = (
        "Six sealed boxes: prizes, a dud and two bombs. Everyone peeks inside one, then bids live. "
        "Bluff the room into buying your bomb."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"peek": 10.0, "auction": 15.0, "soft": 6.0, "sold": 6.0}

    def start(self) -> None:
        prizes = [PRIZES[i] for i in self.deal("prizes", len(PRIZES), 3)]
        bombs = [BOMBS[i] for i in self.deal("bombs", len(BOMBS), 2)]
        contents = [*prizes, *bombs, DUD]
        self.rng.shuffle(contents)
        self.contents = [{"emoji": e, "name": n, "value": v} for e, n, v in contents]
        order = list(range(BOX_COUNT))
        self.rng.shuffle(order)
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        self.peeks = {pid: order[i % BOX_COUNT] for i, pid in enumerate(ids)}
        self.extra_peeks: dict[str, int] = {}  # power-card peeks
        self.coins = {pid: START_COINS for pid in self.player_ids}
        self.sold: list[dict[str, Any] | None] = [None] * BOX_COUNT  # once a box is done
        self.round = 0
        self.phase = "peek"
        self.set_deadline(self.timings["peek"])
        self.bump()

    def _open_auction(self) -> None:
        self.high: dict[str, Any] | None = None
        self.bids: list[dict[str, Any]] = []
        self.claims: dict[str, int] = {}
        self.phase = "auction"
        self.set_deadline(self.timings["auction"])
        self.bump()

    def _hammer(self) -> None:
        box = self.contents[self.round]
        record: dict[str, Any] = {"box": self.round, **box, "winner": None, "price": 0}
        if self.high is not None:
            who, price = self.high["player"], self.high["amount"]
            self.coins[who] -= price
            self.add_points(who, box["value"] - price)
            record.update(winner=who, price=price)
        record["peekers"] = sorted(p for p, b in self.peeks.items() if b == self.round)
        self.sold[self.round] = record
        self.phase = "sold"
        self.set_deadline(self.timings["sold"])
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if self.phase != "auction":
            raise GameError("wrong_phase", "Wait for the next box")
        if kind == "say":
            if pid in self.claims:
                raise GameError("already_said", "One claim per box")
            self.claims[pid] = as_int(action.get("line"), lo=0, hi=len(CLAIMS) - 1, field="Claim")
            self.bump()
            return
        if kind != "bid":
            raise GameError("bad_action", "Unknown action")
        amount = as_int(action.get("amount"), lo=MIN_BID, hi=START_COINS, field="Bid")
        if self.high is not None and self.high["player"] == pid:
            raise GameError("already_high", "You're already the top bidder")
        floor = MIN_BID if self.high is None else self.high["amount"] + STEP
        if amount < floor:
            raise GameError("too_low", f"Bid at least {floor}")
        if amount > self.coins[pid]:
            raise GameError("too_high", "You don't have that many coins")
        self.high = {"player": pid, "amount": amount}
        self.bids.append(dict(self.high))
        # Soft close: a late bid always leaves the room a few seconds to answer it.
        left = self.remaining() or 0.0
        if left < self.timings["soft"]:
            self.set_deadline(self.timings["soft"])
        self.bump()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "peek":
            self._open_auction()
        elif self.phase == "auction":
            self._hammer()
        elif self.round + 1 >= BOX_COUNT:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._open_auction()

    def peek(self, pid: str) -> str | None:
        """Power card: look inside one more unsold box."""
        if pid not in self.peeks or self.finished:
            return None
        start = self.round if self.phase in ("peek", "auction") else self.round + 1
        hidden = [i for i in range(start, BOX_COUNT) if i != self.peeks[pid]]
        if not hidden:
            return None
        i = self.rng.choice(hidden)
        self.extra_peeks[pid] = i
        c = self.contents[i]
        return f"Box {LABELS[i]} holds {c['emoji']} {c['name']} ({c['value']:+})."

    def view_for(self, pid: str) -> dict[str, Any]:
        mine = self.peeks.get(pid)
        extra = self.extra_peeks.get(pid)
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": BOX_COUNT,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "labels": list(LABELS),
            "current": self.round,
            "coins": dict(self.coins),
            "boxes": [s for s in self.sold],  # contents only once sold
            "claims_list": list(CLAIMS),
            "you": {
                "peek": None if mine is None else {"box": mine, **self.contents[mine]},
                "extra": None if extra is None else {"box": extra, **self.contents[extra]},
            },
        }
        if self.phase in ("auction", "sold"):
            view["high"] = self.high
            view["bids"] = self.bids[-8:]
            view["claims"] = {p: CLAIMS[i] for p, i in self.claims.items()}
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        done = [s for s in self.sold if s and s["winner"]]
        booms = [s for s in done if s["value"] < 0]
        if booms:
            worst = min(booms, key=lambda s: s["value"] - s["price"])
            out.append(
                {
                    "icon": "💥",
                    "title": "Kaboom",
                    "text": f"{self.name_of(worst['winner'])} paid {worst['price']} for {worst['emoji']} "
                    f"{worst['name']}",
                }
            )
        steals = [s for s in done if s["value"] > s["price"]]
        if steals:
            best = max(steals, key=lambda s: s["value"] - s["price"])
            out.append(
                {
                    "icon": "🔨",
                    "title": "Steal of the night",
                    "text": f"{self.name_of(best['winner'])} got {best['emoji']} worth {best['value']} "
                    f"for {best['price']}",
                }
            )
        for s in booms:  # a peeker who knew it was a bomb and still talked someone into it
            sellers = [p for p in s["peekers"] if p != s["winner"]]
            if sellers:
                out.append(
                    {
                        "icon": "🎭",
                        "title": "Master bluffer",
                        "text": f"{self.name_of(sellers[0])} knew box {LABELS[s['box']]} was a bomb. "
                        f"{self.name_of(s['winner'])} bought it anyway",
                    }
                )
                break
        return out

    def summary(self) -> dict[str, Any]:
        done = [s for s in self.sold if s]
        return {"players": len(self.players), "unsold": sum(1 for s in done if not s["winner"])}
