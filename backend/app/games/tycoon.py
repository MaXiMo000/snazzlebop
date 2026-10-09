"""Property Tycoon: the classic property-trading board game (Monopoly rules), with our own board and cards.

Rules (the official ones):
- Everyone starts with $1,500 and collects $200 for passing or landing on GO.
- Roll two dice and move. Doubles roll again; a third double in a row goes straight to jail.
- Land on an unowned street, station or utility: buy it at its price, or it goes to auction (everyone can
  bid, including you; the clock restarts with each bid).
- Land on someone else's: pay rent. Streets: double rent on an unbuilt street when the owner has the whole
  colour set; houses and hotels raise it. Stations: $25/50/100/200 for 1-4 owned. Utilities: 4x the dice
  (10x with both). Mortgaged property collects no rent.
- Houses: only on a full colour set with nothing mortgaged in it, built evenly; a hotel after four houses.
  The bank has 32 houses and 12 hotels. Selling a building pays half its cost (evenly too).
- Mortgage for half the price; unmortgaging costs that plus 10%. No mortgages in a set with buildings.
- Jail: pay $50 before rolling, use a Get Out of Jail Free card, or try for doubles (three tries; after
  the third miss you pay $50 and move). Just Visiting is safe. Free Parking does nothing.
- Surprise and Community Fund cards (16 each, our own text), Income Tax $200, Luxury Tax $100.
- Can't pay? Mortgage and sell to raise the money, or go bankrupt: everything goes to whoever you owe
  (the bank's properties go back on sale).
- "Call it a night": when everyone still playing votes for it, the game ends now and the richest wins.
- Trade with anyone at any time: streets, cash and Get Out of Jail Free cards (sell a set's buildings
  first). Taking a mortgaged property costs the 10% interest straight away.

Party length (our only change): the host picks 30/45/60 minutes or "no limit". When the time is up the
game ends after the current turn and the richest player (cash + property + buildings) wins. Every step
has a clock so nobody waits for a sleepy phone: roll, buy, manage, raise money.

Scoring: survivors score their final net worth in dollars; bankrupt players score their place in the
order they went out (1 for the first), so they rank below everyone still standing.

Everything is public, as at a real table, except the order of the two card decks.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

START_CASH = 1500
GO_SALARY = 200
JAIL, GO_TO_JAIL = 10, 30
JAIL_FINE = 50
HOUSES, HOTELS = 32, 12
LENGTHS = {"45": 45, "30": 30, "60": 60, "0": 0}
KEEP_LOG = 40
AUCTION_RESTART = 8.0

# fmt: off
# kind, name, group, price, house cost, rents (base, 1-4 houses, hotel)
STREETS: dict[int, tuple[str, str, int, int, tuple[int, ...]]] = {
    1: ("Pebble Lane", "brown", 60, 50, (2, 10, 30, 90, 160, 250)),
    3: ("Mossy Row", "brown", 60, 50, (4, 20, 60, 180, 320, 450)),
    6: ("Kite Street", "sky", 100, 50, (6, 30, 90, 270, 400, 550)),
    8: ("Bluebell Way", "sky", 100, 50, (6, 30, 90, 270, 400, 550)),
    9: ("Puddle Park", "sky", 120, 50, (8, 40, 100, 300, 450, 600)),
    11: ("Candy Court", "pink", 140, 100, (10, 50, 150, 450, 625, 750)),
    13: ("Rose Walk", "pink", 140, 100, (10, 50, 150, 450, 625, 750)),
    14: ("Flamingo Drive", "pink", 160, 100, (12, 60, 180, 500, 700, 900)),
    16: ("Marigold Avenue", "orange", 180, 100, (14, 70, 200, 550, 750, 950)),
    18: ("Pumpkin Plaza", "orange", 180, 100, (14, 70, 200, 550, 750, 950)),
    19: ("Sunset Strip", "orange", 200, 100, (16, 80, 220, 600, 800, 1000)),
    21: ("Cherry Square", "red", 220, 150, (18, 90, 250, 700, 875, 1050)),
    23: ("Ruby Road", "red", 220, 150, (18, 90, 250, 700, 875, 1050)),
    24: ("Lantern Lane", "red", 240, 150, (20, 100, 300, 750, 925, 1100)),
    26: ("Honey Hill", "yellow", 260, 150, (22, 110, 330, 800, 975, 1150)),
    27: ("Sunflower Street", "yellow", 260, 150, (22, 110, 330, 800, 975, 1150)),
    29: ("Lemon Grove", "yellow", 280, 150, (24, 120, 360, 850, 1025, 1200)),
    31: ("Fern Gardens", "green", 300, 200, (26, 130, 390, 900, 1100, 1275)),
    32: ("Mint Terrace", "green", 300, 200, (26, 130, 390, 900, 1100, 1275)),
    34: ("Emerald Heights", "green", 320, 200, (28, 150, 450, 1000, 1200, 1400)),
    37: ("Starlight Boulevard", "navy", 350, 200, (35, 175, 500, 1100, 1300, 1500)),
    39: ("Moonbeam Bay", "navy", 400, 200, (50, 200, 600, 1400, 1700, 2000)),
}
STATIONS = {5: "North Station", 15: "East Station", 25: "South Station", 35: "West Station"}
UTILITIES = {12: "Power Plant", 28: "Water Tower"}
OTHER = {
    0: ("go", "GO"), 2: ("fund", "Community Fund"), 4: ("tax", "Income Tax"), 7: ("chance", "Surprise"),
    10: ("jail", "Jail"), 17: ("fund", "Community Fund"), 20: ("parking", "Free Parking"),
    22: ("chance", "Surprise"), 30: ("gotojail", "Go to Jail"), 33: ("fund", "Community Fund"),
    36: ("chance", "Surprise"), 38: ("tax", "Luxury Tax"),
}
TAXES = {4: 200, 38: 100}
GROUPS: dict[str, list[int]] = {}
for _sq, _s in STREETS.items():
    GROUPS.setdefault(_s[1], []).append(_sq)

# Cards: (text, effect, value). Effects: goto (square; collect on passing GO), station (nearest, pay
# double), utility (nearest, pay 10x a fresh roll), back (spaces), jail, free (get out of jail free),
# get / pay (bank), repairs ((per house, per hotel)), each_pay (to every player), each_get (from
# every player).
SURPRISE: list[tuple[str, str, Any]] = [
    ("Rocket roller skates! Advance to GO and collect $200.", "goto", 0),
    ("Your aunt invites you for tea on Cherry Square. Advance there.", "goto", 21),
    ("You won a free manicure on Candy Court. Advance there.", "goto", 11),
    ("Take the express to the nearest station. If it's owned, pay the owner double rent.", "station", None),
    ("Wrong platform! Go to the nearest station. If it's owned, pay double rent.", "station", None),
    ("Kettle fuse! Go to the nearest utility. If it's owned, roll and pay 10x the dice.", "utility", None),
    ("Your lemonade stand made a profit. Collect $50.", "get", 50),
    ("A friendly ghost gives you a Get Out of Jail Free card. Keep it until needed.", "free", None),
    ("You forgot your keys. Go back 3 spaces.", "back", 3),
    ("Caught dancing in the fountain. Go directly to jail. Do not pass GO.", "jail", None),
    ("Your whole street needs new gutters: pay $25 per house and $100 per hotel.", "repairs", (25, 100)),
    ("Parking ticket for your tandem bicycle. Pay $15.", "pay", 15),
    ("Sightseeing day: take a trip to North Station.", "goto", 5),
    ("A limousine whisks you to Moonbeam Bay.", "goto", 39),
    ("You were voted party organiser. Pay each player $50 for snacks.", "each_pay", 50),
    ("Your old piggy bank turned up. Collect $150.", "get", 150),
]
FUND: list[tuple[str, str, Any]] = [
    ("A street parade carries you to GO. Collect $200.", "goto", 0),
    ("The bank made a mistake in your favour. Collect $200.", "get", 200),
    ("Your cat swallowed a sock. Vet bill: pay $50.", "pay", 50),
    ("You sold your old comic books. Collect $50.", "get", 50),
    ("The mayor owes you one: a Get Out of Jail Free card. Keep it until needed.", "free", None),
    ("Your rubber duck was smuggling bubbles. Go directly to jail. Do not pass GO.", "jail", None),
    ("Your holiday savings paid off. Collect $100.", "get", 100),
    ("A tax refund arrived. Collect $20.", "get", 20),
    ("It's your birthday! Collect $10 from every player.", "each_get", 10),
    ("Your insurance paid out. Collect $100.", "get", 100),
    ("Sprained ankle at the roller disco. Pay $100.", "pay", 100),
    ("Pottery class fees. Pay $50.", "pay", 50),
    ("You walked the neighbour's dogs. Collect $25.", "get", 25),
    ("The town fixes your road: pay $40 per house and $115 per hotel.", "repairs", (40, 115)),
    ("Second prize in the sandcastle contest. Collect $10.", "get", 10),
    ("A long-lost uncle left you $100.", "get", 100),
]
# fmt: on
DECKS = {"chance": SURPRISE, "fund": FUND}


def space_kind(sq: int) -> str:
    if sq in STREETS:
        return "street"
    if sq in STATIONS:
        return "station"
    if sq in UTILITIES:
        return "utility"
    return OTHER[sq][0]


def space_name(sq: int) -> str:
    if sq in STREETS:
        return STREETS[sq][0]
    return STATIONS.get(sq) or UTILITIES.get(sq) or OTHER[sq][1]


def price_of(sq: int) -> int:
    if sq in STREETS:
        return STREETS[sq][2]
    return 200 if sq in STATIONS else 150 if sq in UTILITIES else 0


def _interest(mortgage: int) -> int:
    """10% of a mortgage, rounded up (whole dollars: no float surprises)."""
    return (mortgage + 9) // 10


def _with_interest(mortgage: int) -> int:
    return mortgage + _interest(mortgage)


def board() -> list[dict[str, Any]]:
    """The board, for the screens (static)."""
    out = []
    for sq in range(40):
        kind = space_kind(sq)
        item: dict[str, Any] = {"kind": kind, "name": space_name(sq)}
        if kind == "street":
            _, group, price, house, rents = STREETS[sq]
            item |= {"group": group, "price": price, "house": house, "rents": list(rents)}
        elif kind in ("station", "utility"):
            item["price"] = price_of(sq)
        elif kind == "tax":
            item["tax"] = TAXES[sq]
        out.append(item)
    return out


BOARD = board()


class PropertyTycoon(Game):
    game_id: ClassVar[str] = "tycoon"
    title: ClassVar[str] = "Property Tycoon"
    blurb: ClassVar[str] = (
        "Buy streets, build houses and hotels, charge rent and trade your way to a fortune. Bankrupt "
        "everyone, or be the richest when the clock runs out."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"length": ["45", "30", "60", "0"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Roll and go round the board. Buy what you land on, or it goes to auction.",
        "Land on someone else's and pay rent. A whole colour set doubles it; then build houses and hotels.",
        "Doubles roll again; three in a row and you're off to jail. Pass GO to collect $200.",
        "Short of cash? Mortgage or sell buildings. Can't pay at all and you're bankrupt.",
        "Trade with anyone, any time. When the clock runs out, the richest player wins.",
    )

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"roll": 30.0, "buy": 20.0, "auction": 12.0, "manage": 30.0, "debt": 45.0}

    # -- setup ----------------------------------------------------------------------------------------
    def start(self) -> None:
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        minutes = LENGTHS.get(self.options.get("length", "45"), 45)
        self.ends_at: float | None = self.clock() + minutes * 60 if minutes else None
        self.cash = dict.fromkeys(self.order, START_CASH)
        self.pos = dict.fromkeys(self.order, 0)
        self.jail: dict[str, int] = {}  # player -> failed tries so far (present = in jail)
        self.free_cards: dict[str, list[str]] = {p: [] for p in self.order}
        self.out: list[str] = []  # bankrupt, in the order they went out
        self.owner: dict[int, str] = {}
        self.houses: dict[int, int] = {}  # 5 = hotel
        self.mortgaged: set[int] = set()
        self.piles = {name: self._shuffled(len(cards)) for name, cards in DECKS.items()}
        self.log: list[dict[str, Any]] = []
        self.dice: tuple[int, int] | None = None
        self.turn = -1
        self.current = self.order[0]
        self.doubles = 0
        self.must_roll = False
        self.offer: int | None = None  # a square the current player may buy
        self.auction: dict[str, Any] | None = None
        self.debts: list[dict[str, Any]] = []  # {"pid", "amount", "to"} ("to" None = the bank)
        self.trades: dict[int, dict[str, Any]] = {}
        self.next_trade = 1
        self.stats: dict[str, dict[str, int]] = {
            p: {"rent_paid": 0, "rent_got": 0, "biggest": 0} for p in self.order
        }
        self.turns_taken = 0
        self.call_it: set[str] = set()  # players voting to end the game now
        self.waits = 0  # one per new wait (each call to _continue): identifies the wait for the host's skip
        self._next_turn()

    def _shuffled(self, n: int) -> list[int]:
        cards = list(range(n))
        self.rng.shuffle(cards)
        return cards

    def _say(self, kind: str, **data: Any) -> None:
        self.log.append({"type": kind, **data})
        self.log = self.log[-KEEP_LOG:]

    @property
    def alive(self) -> list[str]:
        return [p for p in self.order if p not in self.out]

    @property
    def stage(self) -> str:
        return f"{self.phase}:{self.turns_taken}:{self.waits}"

    # -- the turn machine -----------------------------------------------------------------------------
    def _next_turn(self) -> None:
        if self.ends_at is not None and self.turn >= 0 and self.clock() >= self.ends_at:
            return self._finish("time")
        alive = self.alive
        if len(alive) <= 1:
            return self._finish("last")
        i = self.order.index(self.current)
        for step in range(1, len(self.order) + 1):
            nxt = self.order[(i + step) % len(self.order)] if self.turn >= 0 else self.order[0]
            if nxt not in self.out:
                break
        self.turn += 1
        self.turns_taken += 1
        self.current = nxt
        self.doubles = 0
        self.must_roll = True
        self.dice = None
        self._continue()

    def _continue(self) -> None:
        """Pick the phase from what is still waiting: debts first, then an auction, a purchase, a roll."""
        if self.finished:
            return
        self.round = self.turn
        self.waits += 1
        if self.debts:
            self.phase = "debt"
            self.set_deadline(self.timings["debt"])
        elif self.auction is not None:
            self.phase = "auction"
            self.deadline = self.auction["deadline"]
        elif self.offer is not None:
            self.phase = "buy"
            self.set_deadline(self.timings["buy"])
        elif self.must_roll and self.current not in self.out:
            self.phase = "roll"
            self.set_deadline(self.timings["roll"])
        elif self.current in self.out:
            return self._next_turn()
        else:
            self.phase = "manage"
            self.set_deadline(self.timings["manage"])
        self.bump()

    def _finish(self, why: str) -> None:
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.offer, self.auction, self.debts, self.trades = None, None, [], {}
        self._say("end", why=why)
        for p in self.order:
            self.round_scores[p] = self.worth(p) if p not in self.out else self.out.index(p) + 1
        self.bump()

    # -- money ----------------------------------------------------------------------------------------
    def worth(self, pid: str) -> int:
        total = self.cash[pid]
        for sq, who in self.owner.items():
            if who != pid:
                continue
            total += price_of(sq) // 2 if sq in self.mortgaged else price_of(sq)
            if sq in STREETS:
                total += self.houses.get(sq, 0) * STREETS[sq][3]
        return total

    def _raisable(self, pid: str) -> int:
        """Cash plus everything the player could still sell or mortgage."""
        total = self.cash[pid]
        for sq, who in self.owner.items():
            if who != pid:
                continue
            if sq in STREETS:
                total += self.houses.get(sq, 0) * STREETS[sq][3] // 2
            if sq not in self.mortgaged:
                total += price_of(sq) // 2
        return total

    def _owe(self, pid: str, amount: int, to: str | None, why: str) -> None:
        """Pay now if the cash is there, otherwise queue a debt (the player must raise it or go bust)."""
        if amount <= 0:
            return
        if self.cash[pid] >= amount:
            self._transfer(pid, amount, to)
            self._say("pay", player=pid, amount=amount, to=to, why=why)
        else:
            self.debts.append({"pid": pid, "amount": amount, "to": to, "why": why})

    def _transfer(self, pid: str, amount: int, to: str | None) -> None:
        self.cash[pid] -= amount
        if to is not None:
            self.cash[to] += amount

    def _collect(self, pid: str, amount: int, why: str) -> None:
        self.cash[pid] += amount
        self._say("get", player=pid, amount=amount, why=why)

    # -- moving ---------------------------------------------------------------------------------------
    def _roll_dice(self) -> tuple[int, int]:
        return self.rng.randint(1, 6), self.rng.randint(1, 6)

    def _move_to(self, pid: str, sq: int, *, collect: bool = True) -> None:
        if collect and sq < self.pos[pid]:
            self._collect(pid, GO_SALARY, "go")
        self.pos[pid] = sq

    def _to_jail(self, pid: str) -> None:
        self.pos[pid] = JAIL
        self.jail[pid] = 0
        if pid == self.current:
            self.must_roll = False
        self._say("jail", player=pid)

    def _land(self, pid: str, roll: int, *, rent_times: int = 1, utility_ten: bool = False) -> None:
        sq = self.pos[pid]
        kind = space_kind(sq)
        if kind in ("street", "station", "utility"):
            owner = self.owner.get(sq)
            if owner is None:
                self.offer = sq
            elif owner != pid and sq not in self.mortgaged and owner not in self.out:
                if utility_ten:
                    d = self._roll_dice()
                    roll = sum(d)
                    self._say("roll", player=pid, dice=list(d), why="utility")
                rent = self.rent(sq, roll, ten=utility_ten) * rent_times
                self.stats[pid]["rent_paid"] += rent
                self.stats[owner]["rent_got"] += rent
                self.stats[owner]["biggest"] = max(self.stats[owner]["biggest"], rent)
                self._owe(pid, rent, owner, f"rent:{sq}")
        elif kind == "tax":
            self._owe(pid, TAXES[sq], None, f"tax:{sq}")
        elif kind in ("chance", "fund"):
            self._draw(pid, kind)
        elif kind == "gotojail":
            self._to_jail(pid)

    def rent(self, sq: int, roll: int, *, ten: bool = False) -> int:
        owner = self.owner[sq]
        if sq in STREETS:
            rents = STREETS[sq][4]
            built = self.houses.get(sq, 0)
            if built:
                return rents[built]
            group = GROUPS[STREETS[sq][1]]
            return rents[0] * (2 if all(self.owner.get(s) == owner for s in group) else 1)
        if sq in STATIONS:
            n = sum(1 for s in STATIONS if self.owner.get(s) == owner)
            return 25 * 2 ** (n - 1)
        n = sum(1 for s in UTILITIES if self.owner.get(s) == owner)
        return roll * (10 if ten or n == 2 else 4)

    def _draw(self, pid: str, deck: str) -> None:
        cards = self.piles[deck]
        if not cards:
            held = {f"{deck}:{i}" for hand in self.free_cards.values() for i in hand}
            cards.extend(self._shuffled_except(deck, held))
        index = cards.pop(0)
        text, effect, value = DECKS[deck][index]
        self._say("card", player=pid, deck=deck, text=text)
        if effect == "free":
            self.free_cards[pid].append(f"{deck}:{index}")
            return
        cards.append(index)  # back on the bottom
        if effect == "goto":
            self._move_to(pid, value)
            self._land(pid, sum(self.dice or (0, 0)))
        elif effect == "station":
            sq = next(
                s for s in sorted(STATIONS, key=lambda s: (s - self.pos[pid]) % 40) if s != self.pos[pid]
            )
            self._move_to(pid, sq)
            self._land(pid, 0, rent_times=2)
        elif effect == "utility":
            sq = min(UTILITIES, key=lambda s: (s - self.pos[pid]) % 40 or 40)
            self._move_to(pid, sq)
            self._land(pid, 0, utility_ten=True)
        elif effect == "back":
            self.pos[pid] = (self.pos[pid] - value) % 40
            self._land(pid, sum(self.dice or (0, 0)))
        elif effect == "jail":
            self._to_jail(pid)
        elif effect == "get":
            self._collect(pid, value, "card")
        elif effect == "pay":
            self._owe(pid, value, None, "card")
        elif effect == "repairs":
            per_house, per_hotel = value
            houses = sum(h for s, h in self.houses.items() if self.owner.get(s) == pid and h < 5)
            hotels = sum(1 for s, h in self.houses.items() if self.owner.get(s) == pid and h == 5)
            self._owe(pid, houses * per_house + hotels * per_hotel, None, "repairs")
        elif effect == "each_pay":
            for other in self.alive:
                if other != pid:
                    self._owe(pid, value, other, "card")
        elif effect == "each_get":
            for other in self.alive:
                if other != pid:
                    self._owe(other, value, pid, "birthday")

    def _shuffled_except(self, deck: str, held: set[str]) -> list[int]:
        return [i for i in self._shuffled(len(DECKS[deck])) if f"{deck}:{i}" not in held]

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if self.finished:
            raise GameError("finished", "The game is over")
        if pid in self.out:
            raise GameError("bankrupt", "You're out of the game")
        kind = action.get("a")
        handlers = {
            "roll": self._act_roll,
            "pay_fine": self._act_pay_fine,
            "use_card": self._act_use_card,
            "buy": self._act_buy,
            "decline": self._act_decline,
            "bid": self._act_bid,
            "end": self._act_end,
            "build": self._act_build,
            "sell": self._act_sell,
            "mortgage": self._act_mortgage,
            "unmortgage": self._act_unmortgage,
            "pay_debt": self._act_pay_debt,
            "bankrupt": self._act_bankrupt,
            "offer": self._act_offer,
            "accept": self._act_accept,
            "reject": self._act_reject,
            "call_it": self._act_call_it,
        }
        handler = handlers.get(kind) if isinstance(kind, str) else None
        if handler is None:
            raise GameError("bad_action", "Unknown action")
        handler(pid, action)
        self.bump()

    def _my_turn(self, pid: str, phase: str) -> None:
        if pid != self.current:
            raise GameError("not_your_turn", "It's not your turn")
        if self.phase != phase:
            raise GameError("wrong_phase", "Not now")

    def _act_roll(self, pid: str, _: dict[str, Any]) -> None:
        self._my_turn(pid, "roll")
        d1, d2 = self._roll_dice()
        self.dice = (d1, d2)
        self._say("roll", player=pid, dice=[d1, d2])
        doubles = d1 == d2
        if pid in self.jail:
            if doubles:
                del self.jail[pid]
                self._say("free", player=pid, how="doubles")
                self.must_roll = False  # out on doubles, but no extra roll
            else:
                self.jail[pid] += 1
                if self.jail[pid] < 3:
                    self.must_roll = False
                    return self._continue()
                del self.jail[pid]
                self._owe(pid, JAIL_FINE, None, "fine")
                self._say("free", player=pid, how="fine")
                self.must_roll = False
        else:
            self.doubles = self.doubles + 1 if doubles else 0
            if self.doubles == 3:
                self._to_jail(pid)
                return self._continue()
            self.must_roll = doubles
        self._move_to(pid, (self.pos[pid] + d1 + d2) % 40)
        self._land(pid, d1 + d2)
        self._continue()

    def _act_pay_fine(self, pid: str, _: dict[str, Any]) -> None:
        self._my_turn(pid, "roll")
        if pid not in self.jail:
            raise GameError("not_in_jail", "You're not in jail")
        if self.cash[pid] < JAIL_FINE:
            raise GameError("no_cash", "You need $50")
        self._transfer(pid, JAIL_FINE, None)
        del self.jail[pid]
        self._say("free", player=pid, how="paid")

    def _act_use_card(self, pid: str, _: dict[str, Any]) -> None:
        self._my_turn(pid, "roll")
        if pid not in self.jail or not self.free_cards[pid]:
            raise GameError("no_card", "No card to use")
        card = self.free_cards[pid].pop(0)
        deck, index = card.split(":")
        self.piles[deck].append(int(index))
        del self.jail[pid]
        self._say("free", player=pid, how="card")

    def _act_buy(self, pid: str, _: dict[str, Any]) -> None:
        self._my_turn(pid, "buy")
        sq = self.offer
        if sq is None:
            raise GameError("wrong_phase", "Nothing to buy")
        if self.cash[pid] < price_of(sq):
            raise GameError("no_cash", "Not enough cash: auction it, or mortgage something first")
        self._transfer(pid, price_of(sq), None)
        self.owner[sq] = pid
        self.offer = None
        self._say("buy", player=pid, square=sq, amount=price_of(sq))
        self._continue()

    def _act_decline(self, pid: str, _: dict[str, Any]) -> None:
        self._my_turn(pid, "buy")
        self._start_auction()

    def _start_auction(self) -> None:
        sq = self.offer
        self.offer = None
        self.auction = {
            "square": sq,
            "bid": 0,
            "bidder": None,
            "deadline": self.clock() + self.timings["auction"],
        }
        self._say("auction", square=sq)
        self._continue()

    def _act_bid(self, pid: str, action: dict[str, Any]) -> None:
        if self.phase != "auction" or self.auction is None:
            raise GameError("wrong_phase", "No auction right now")
        amount = as_int(action.get("amount"), lo=1, hi=100000, field="bid")
        if amount <= self.auction["bid"]:
            raise GameError("too_low", f"Bid more than ${self.auction['bid']}")
        if amount > self.cash[pid]:
            raise GameError("no_cash", "You don't have that much cash")
        self.auction["bid"], self.auction["bidder"] = amount, pid
        self.auction["deadline"] = max(self.auction["deadline"], self.clock() + AUCTION_RESTART)
        self.deadline = self.auction["deadline"]

    def _end_auction(self) -> None:
        a = self.auction
        if a is None:
            return
        self.auction = None
        if a["bidder"] is not None and self.cash[a["bidder"]] >= a["bid"]:
            self._transfer(a["bidder"], a["bid"], None)
            self.owner[a["square"]] = a["bidder"]
            self._say("won", player=a["bidder"], square=a["square"], amount=a["bid"])
        else:
            self._say("unsold", square=a["square"])
        self._continue()

    def _act_end(self, pid: str, _: dict[str, Any]) -> None:
        self._my_turn(pid, "manage")
        self._next_turn()

    # building, selling and mortgages: on your own turn (roll or manage), or when you owe money
    def _may_manage(self, pid: str, *, raising: bool) -> None:
        if self.phase == "debt" and self.debts and self.debts[0]["pid"] == pid:
            if not raising:
                raise GameError("in_debt", "Pay what you owe first")
            return
        if pid != self.current or self.phase not in ("roll", "manage", "buy"):
            raise GameError("not_your_turn", "You can do that on your turn")

    def _own_square(self, pid: str, raw: Any) -> int:
        sq = as_int(raw, lo=0, hi=39, field="square")
        if self.owner.get(sq) != pid:
            raise GameError("not_yours", "You don't own that")
        return sq

    def _act_build(self, pid: str, action: dict[str, Any]) -> None:
        self._may_manage(pid, raising=False)
        sq = self._own_square(pid, action.get("square"))
        if sq not in STREETS:
            raise GameError("not_street", "You can only build on streets")
        group = GROUPS[STREETS[sq][1]]
        if any(self.owner.get(s) != pid for s in group):
            raise GameError("no_set", "You need the whole colour set first")
        if any(s in self.mortgaged for s in group):
            raise GameError("mortgaged", "Unmortgage the set first")
        level = self.houses.get(sq, 0)
        if level >= 5:
            raise GameError("full", "That street already has a hotel")
        if level > min(self.houses.get(s, 0) for s in group):
            raise GameError("uneven", "Build evenly: the other streets in the set first")
        if level == 4:
            if self._hotels_left() < 1:
                raise GameError("no_hotels", "The bank is out of hotels")
        elif self._houses_left() < 1:
            raise GameError("no_houses", "The bank is out of houses")
        cost = STREETS[sq][3]
        if self.cash[pid] < cost:
            raise GameError("no_cash", f"A building here costs ${cost}")
        self._transfer(pid, cost, None)
        self.houses[sq] = level + 1
        self._say("build", player=pid, square=sq, level=level + 1)

    def _act_sell(self, pid: str, action: dict[str, Any]) -> None:
        self._may_manage(pid, raising=True)
        sq = self._own_square(pid, action.get("square"))
        level = self.houses.get(sq, 0)
        if level == 0:
            raise GameError("nothing", "No buildings to sell there")
        group = GROUPS[STREETS[sq][1]]
        if level < max(self.houses.get(s, 0) for s in group):
            raise GameError("uneven", "Sell evenly: the other streets in the set first")
        if level == 5 and self._houses_left() < 4:
            raise GameError("no_houses", "The bank hasn't got 4 houses to swap for the hotel")
        self.houses[sq] = level - 1
        self.cash[pid] += STREETS[sq][3] // 2
        self._say("sell", player=pid, square=sq, level=level - 1)

    def _act_mortgage(self, pid: str, action: dict[str, Any]) -> None:
        self._may_manage(pid, raising=True)
        sq = self._own_square(pid, action.get("square"))
        if sq in self.mortgaged:
            raise GameError("mortgaged", "Already mortgaged")
        if sq in STREETS and any(self.houses.get(s, 0) for s in GROUPS[STREETS[sq][1]]):
            raise GameError("buildings", "Sell the set's buildings first")
        self.mortgaged.add(sq)
        self.cash[pid] += price_of(sq) // 2
        self._say("mortgage", player=pid, square=sq)

    def _act_unmortgage(self, pid: str, action: dict[str, Any]) -> None:
        self._may_manage(pid, raising=False)
        sq = self._own_square(pid, action.get("square"))
        if sq not in self.mortgaged:
            raise GameError("not_mortgaged", "That isn't mortgaged")
        cost = _with_interest(price_of(sq) // 2)
        if self.cash[pid] < cost:
            raise GameError("no_cash", f"Unmortgaging costs ${cost}")
        self._transfer(pid, cost, None)
        self.mortgaged.discard(sq)
        self._say("unmortgage", player=pid, square=sq)

    def _houses_left(self) -> int:
        return HOUSES - sum(h for h in self.houses.values() if h < 5)

    def _hotels_left(self) -> int:
        return HOTELS - sum(1 for h in self.houses.values() if h == 5)

    # debts
    def _act_pay_debt(self, pid: str, _: dict[str, Any]) -> None:
        if self.phase != "debt" or self.debts[0]["pid"] != pid:
            raise GameError("wrong_phase", "You don't owe anything")
        debt = self.debts[0]
        if self.cash[pid] < debt["amount"]:
            raise GameError("no_cash", f"Raise ${debt['amount'] - self.cash[pid]} more first")
        self.debts.pop(0)
        self._transfer(pid, debt["amount"], debt["to"])
        self._say("pay", player=pid, amount=debt["amount"], to=debt["to"], why=debt["why"])
        self._continue()

    def _act_bankrupt(self, pid: str, _: dict[str, Any]) -> None:
        if self.phase != "debt" or self.debts[0]["pid"] != pid:
            raise GameError("wrong_phase", "You can only go bankrupt when you can't pay")
        self._bust(pid)

    def _liquidate(self, pid: str) -> None:
        """Out of time while owing: sell buildings, then mortgage, until the debt is covered."""
        need = self.debts[0]["amount"]
        for sq in sorted((s for s, w in self.owner.items() if w == pid), key=price_of):
            while self.cash[pid] < need and self.houses.get(sq, 0):
                group = GROUPS[STREETS[sq][1]]
                top = max(group, key=lambda s: self.houses.get(s, 0))
                self.houses[top] -= 1
                self.cash[pid] += STREETS[top][3] // 2
        for sq in sorted((s for s, w in self.owner.items() if w == pid), key=price_of):
            if self.cash[pid] >= need:
                break
            if sq not in self.mortgaged and not (
                sq in STREETS and any(self.houses.get(s, 0) for s in GROUPS[STREETS[sq][1]])
            ):
                self.mortgaged.add(sq)
                self.cash[pid] += price_of(sq) // 2

    def _bust(self, pid: str) -> None:
        debt = self.debts.pop(0)
        to = debt["to"]
        for sq in [s for s, w in self.owner.items() if w == pid]:
            level = self.houses.pop(sq, 0)
            if level:
                self.cash[pid] += level * STREETS[sq][3] // 2
            if to is None:
                del self.owner[sq]
                self.mortgaged.discard(sq)
            else:
                self.owner[sq] = to
        if to is not None:
            self.cash[to] += self.cash[pid]
            self.free_cards[to].extend(self.free_cards[pid])
        else:
            for card in self.free_cards[pid]:
                deck, index = card.split(":")
                self.piles[deck].append(int(index))
        self.free_cards[pid] = []
        self.cash[pid] = 0
        self.jail.pop(pid, None)
        self.debts = [d for d in self.debts if d["pid"] != pid and d["to"] != pid]
        for tid in [t for t, tr in self.trades.items() if pid in (tr["from"], tr["to"])]:
            del self.trades[tid]
        self.out.append(pid)
        self._say("bankrupt", player=pid, to=to)
        if len(self.alive) <= 1:
            return self._finish("last")
        if pid == self.current:
            self.offer = None
            self.must_roll = False
        self._continue()

    # trades
    def _side(self, pid: str, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) - {"cash", "squares", "cards"}:
            raise GameError("bad_input", "That trade couldn't be read")
        cash = as_int(raw.get("cash", 0), lo=0, hi=100000, field="cash")
        cards = as_int(raw.get("cards", 0), lo=0, hi=2, field="cards")
        squares = raw.get("squares", [])
        if not isinstance(squares, list) or len(squares) > 28:
            raise GameError("bad_input", "That trade couldn't be read")
        picked = sorted({as_int(s, lo=0, hi=39, field="square") for s in squares})
        return {"cash": cash, "squares": picked, "cards": cards}

    def _check_side(self, pid: str, side: dict[str, Any]) -> None:
        if side["cash"] > self.cash[pid]:
            raise GameError("no_cash", f"{self.name_of(pid)} hasn't got ${side['cash']}")
        if side["cards"] > len(self.free_cards[pid]):
            raise GameError("no_card", f"{self.name_of(pid)} hasn't got that many cards")
        for sq in side["squares"]:
            if self.owner.get(sq) != pid:
                raise GameError("not_yours", f"{self.name_of(pid)} doesn't own {space_name(sq)}")
            if sq in STREETS and any(self.houses.get(s, 0) for s in GROUPS[STREETS[sq][1]]):
                raise GameError("buildings", f"Sell the buildings on {space_name(sq)}'s set first")

    def _act_offer(self, pid: str, action: dict[str, Any]) -> None:
        to = action.get("to")
        if not isinstance(to, str) or to not in self.alive or to == pid:
            raise GameError("bad_input", "Trade with whom?")
        give, get = self._side(pid, action.get("give")), self._side(to, action.get("get"))
        if not any((give["cash"], give["squares"], give["cards"], get["cash"], get["squares"], get["cards"])):
            raise GameError("empty", "Put something in the trade")
        self._check_side(pid, give)
        self._check_side(to, get)
        for tid in [t for t, tr in self.trades.items() if tr["from"] == pid]:
            del self.trades[tid]  # one open offer each: a new one replaces it
        self.trades[self.next_trade] = {"from": pid, "to": to, "give": give, "get": get}
        self._say("offer", player=pid, to=to)
        self.next_trade += 1

    def _trade_id(self, raw: Any) -> int:
        tid = as_int(raw, lo=0, hi=10**9, field="trade")
        if tid not in self.trades:
            raise GameError("no_trade", "That offer is gone")
        return tid

    def _act_accept(self, pid: str, action: dict[str, Any]) -> None:
        tid = self._trade_id(action.get("trade"))
        tr = self.trades[tid]
        if tr["to"] != pid:
            raise GameError("not_yours", "That offer isn't for you")
        if self.phase in ("auction", "debt"):
            raise GameError("busy", "Finish the auction or the debt first")
        frm = tr["from"]
        self._check_side(frm, tr["give"])
        self._check_side(pid, tr["get"])
        fee = {
            frm: sum(_interest(price_of(s) // 2) for s in tr["get"]["squares"] if s in self.mortgaged),
            pid: sum(_interest(price_of(s) // 2) for s in tr["give"]["squares"] if s in self.mortgaged),
        }
        if self.cash[pid] - tr["get"]["cash"] + tr["give"]["cash"] < fee[pid]:
            raise GameError("no_cash", f"You'd need ${fee[pid]} for the mortgage interest")
        if self.cash[frm] - tr["give"]["cash"] + tr["get"]["cash"] < fee[frm]:
            raise GameError("no_cash", f"{self.name_of(frm)} can't cover the mortgage interest")
        del self.trades[tid]
        for a, b, side in ((frm, pid, tr["give"]), (pid, frm, tr["get"])):
            self._transfer(a, side["cash"], b)
            for sq in side["squares"]:
                self.owner[sq] = b
            for _ in range(side["cards"]):
                self.free_cards[b].append(self.free_cards[a].pop(0))
        for p, f in fee.items():
            self.cash[p] -= f
        self._say("trade", player=frm, to=pid)
        # A trade may have handed out offers' squares: drop offers that no longer add up.
        for t in list(self.trades):
            other = self.trades[t]
            try:
                self._check_side(other["from"], other["give"])
                self._check_side(other["to"], other["get"])
            except GameError:
                del self.trades[t]

    def _act_reject(self, pid: str, action: dict[str, Any]) -> None:
        tid = self._trade_id(action.get("trade"))
        if pid not in (self.trades[tid]["from"], self.trades[tid]["to"]):
            raise GameError("not_yours", "That offer isn't yours")
        del self.trades[tid]

    def _act_call_it(self, pid: str, action: dict[str, Any]) -> None:
        """ "Call it a night": once everyone still playing agrees, the game ends now (richest wins)."""
        flag = action.get("on", True)
        if not isinstance(flag, bool):
            raise GameError("bad_input", "Yes or no?")
        if flag:
            self.call_it.add(pid)
        else:
            self.call_it.discard(pid)
        if all(p in self.call_it for p in self.alive):
            self._finish("vote")

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        """The clock ran out (or the host skipped): do the sensible thing for the waiting player."""
        if self.finished:
            return
        if self.phase == "roll":
            self._act_roll(self.current, {})
        elif self.phase == "buy":
            self._start_auction()
        elif self.phase == "auction":
            self._end_auction()
        elif self.phase == "manage":
            self._next_turn()
        elif self.phase == "debt":
            pid = self.debts[0]["pid"]
            self._liquidate(pid)
            if self.cash[pid] >= self.debts[0]["amount"]:
                self._act_pay_debt(pid, {})
            else:
                self._bust(pid)
        self.bump()

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.turn + 1,
            "rounds": 0,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "board": BOARD,
            "order": list(self.order),
            "current": self.current if not self.finished else None,
            "dice": list(self.dice) if self.dice else None,
            "doubles": self.doubles,
            "cash": dict(self.cash),
            "worth": {p: self.worth(p) for p in self.order},
            "pos": dict(self.pos),
            "jail": dict(self.jail),
            "cards": {p: len(c) for p, c in self.free_cards.items()},
            "out": list(self.out),
            "owner": {str(s): p for s, p in self.owner.items()},
            "houses": {str(s): h for s, h in self.houses.items() if h},
            "mortgaged": sorted(self.mortgaged),
            "offer": self.offer,
            "auction": (
                {k: self.auction[k] for k in ("square", "bid", "bidder")}
                if self.auction is not None
                else None
            ),
            "debt": dict(self.debts[0]) if self.debts and self.phase == "debt" else None,
            "raisable": {p: self._raisable(p) for p in self.order},
            "trades": [{"id": t, **tr} for t, tr in self.trades.items()],
            "bank": {"houses": self._houses_left(), "hotels": self._hotels_left()},
            "call_it": sorted(self.call_it),
            "ends_in": max(0.0, self.ends_at - self.clock()) if self.ends_at is not None else None,
            "log": self.log[-12:],
            "you": {"playing": pid in self.round_scores, "out": pid in self.out},
            "scores": self.scores(),
        }
        return view

    def peek(self, pid: str) -> str | None:
        top = self.piles["chance"][0] if self.piles["chance"] else None
        return None if top is None else f"The next Surprise card: “{SURPRISE[top][0]}”"

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        landlord = max(self.order, key=lambda p: self.stats[p]["rent_got"])
        if self.stats[landlord]["rent_got"]:
            out.append(
                {
                    "icon": "🏠",
                    "title": "Landlord",
                    "text": f"{self.name_of(landlord)} collected ${self.stats[landlord]['rent_got']:,} rent",
                }
            )
        ouch = max(self.order, key=lambda p: self.stats[p]["biggest"])
        if self.stats[ouch]["biggest"] >= 200:
            out.append(
                {
                    "icon": "💸",
                    "title": "Ouch",
                    "text": f"A ${self.stats[ouch]['biggest']:,} rent went to {self.name_of(ouch)}",
                }
            )
        if self.out:
            out.append(
                {
                    "icon": "📉",
                    "title": "First to fold",
                    "text": f"{self.name_of(self.out[0])} went bankrupt first",
                }
            )
        owned = {p: sum(1 for w in self.owner.values() if w == p) for p in self.order}
        mogul = max(owned, key=lambda p: owned[p])
        if owned[mogul]:
            out.append(
                {
                    "icon": "🗺️",
                    "title": "Mogul",
                    "text": f"{self.name_of(mogul)} ended with {owned[mogul]} properties",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "turns": self.turns_taken,
            "bankrupt": len(self.out),
            "timed": self.ends_at is not None,
        }
