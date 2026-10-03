"""Blackjack Showdown: the room (or just you) at one table against the dealer.

Classic: five hands, 1,000 chips each, bets of 50/100/200/500. Six-deck shoe (reshuffled when it runs
low), dealer peeks for blackjack and stands on soft 17, blackjack pays 3:2. Hit, stand, double on the
first two cards, one split per hand (split aces get one card each). Every phase and turn has a timer:
a missed bet auto-bets the minimum, a missed turn stands. Your game score is your net chips.

Extras: with company you can put a side bet (50/100) on another player's hand along with your own
bet: 1:1 if their hand makes money, refunded on a push. One hand per game is a Chaos hand with a
twist that's only announced when that hand opens. Tournament mode (3+ players): busted players are
out, and from the second hand the single lowest stack is eliminated after every hand; you score for
everyone you outlast, and the last one standing takes a bonus.

Secrecy: the dealer's hole card, the shoe order and the coming Chaos card exist only here until
they're played or announced. Everyone's own cards and all bets are face up, as at a real table.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]
BETS = (50, 100, 200, 500)
SIDE_BETS = (50, 100)
START_CHIPS = 1000
DECKS = 6
OUTLAST_POINTS = 100  # tournament: per player you outlast
CHAMPION_POINTS = 300  # tournament: last one standing
CHAOS: dict[str, dict[str, str]] = {
    "soft17": {"label": "Dealer hits soft 17", "text": "The dealer draws on a soft 17 this hand."},
    "double_pay": {"label": "Double payouts", "text": "Every winning hand pays double this hand."},
    "push_pays": {"label": "Ties pay", "text": "A tie with the dealer pays 1:1 this hand instead of a push."},
}


def card_value(card: str) -> int:
    rank = card[:-1]
    if rank == "A":
        return 11
    return 10 if rank in ("J", "Q", "K") else int(rank)


def hand_value(cards: list[str]) -> tuple[int, bool]:
    """(best total, soft) where soft means an ace is still counting as 11."""
    total = sum(card_value(c) for c in cards)
    aces = sum(1 for c in cards if c.startswith("A"))
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and hand_value(cards)[0] == 21


class BlackjackShowdown(Game):
    game_id: ClassVar[str] = "blackjack"
    title: ClassVar[str] = "Blackjack Showdown"
    blurb: ClassVar[str] = (
        "You (or the whole room) against the dealer. 1,000 chips each: hit, stand, double down, split, "
        "side-bet on friends, survive the Chaos card. Tournament mode knocks out the shortest stack."
    )
    min_players: ClassVar[int] = 1
    max_players: ClassVar[int] = 8
    OPTIONS: ClassVar[dict[str, list[str]]] = {"mode": ["classic", "tournament"]}

    HANDS = 5
    TOURNAMENT_MIN = 3

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"bet": 25.0, "turn": 25.0, "settle": 9.0}

    # -- setup --------------------------------------------------------------
    def start(self) -> None:
        self.mode = self.options.get("mode", "classic")
        if self.mode == "tournament" and len(self.players) < self.TOURNAMENT_MIN:
            raise GameError("bad_player_count", f"Tournament mode needs {self.TOURNAMENT_MIN}+ players")
        # A tournament needs room for every elimination (one per hand from hand 2), plus a little slack.
        self.hands_total = self.HANDS if self.mode == "classic" else len(self.players) + 2
        self.chips: dict[str, int] = {p.id: START_CHIPS for p in self.players}
        self.active: list[str] = list(self.player_ids)  # still in the game (always everyone in classic)
        self.out: list[dict[str, Any]] = []  # tournament knockouts, in order: {"player", "hand", "why"}
        self.shoe: list[str] = []
        self._reshuffle()
        self.chaos_hand = self.rng.randrange(1, self.hands_total)  # never the first hand
        self.chaos_event = self.rng.choice(sorted(CHAOS))
        self.round = 0
        self.history: list[dict[str, Any]] = []
        self.standings: list[str] = []
        self._enter_bet()

    @property
    def chaos(self) -> str | None:
        return self.chaos_event if self.round == self.chaos_hand else None

    def _reshuffle(self) -> None:
        self.shoe = [r + s for _ in range(DECKS) for s in SUITS for r in RANKS]
        self.rng.shuffle(self.shoe)
        self.reshuffled = True

    def _draw(self) -> str:
        if not self.shoe:
            self._reshuffle()
        return self.shoe.pop()

    # -- phases -------------------------------------------------------------
    def _enter_bet(self) -> None:
        if len(self.shoe) < 52:
            self._reshuffle()
        else:
            self.reshuffled = False
        self.bets: dict[str, int] = {}
        self.side: dict[str, dict[str, Any]] = {}  # bettor -> {"on": player, "amount": n}
        self.hands: dict[str, list[dict[str, Any]]] = {}
        self.dealer: list[str] = []
        self.order: list[tuple[str, int]] = []
        self.turn = 0
        self.result: dict[str, Any] | None = None
        self.phase = "bet"
        self.set_deadline(self.timings["bet"])
        self.bump()
        if not self._bettors() or (self.mode == "tournament" and len(self.active) <= 1):
            self._finish_game()

    def _bettors(self) -> list[str]:
        return [pid for pid in self.active if self.chips[pid] >= BETS[0]]

    def _deal(self) -> None:
        for pid in self._bettors():
            if pid not in self.bets:  # missed the timer: minimum bet
                self._place(pid, BETS[0])
        seats = [pid for pid in self.player_ids if pid in self.bets]
        for pid in seats:
            self.hands[pid] = [
                {"cards": [], "bet": self.bets[pid], "done": False, "doubled": False, "split": False}
            ]
        for _ in range(2):
            for pid in seats:
                self.hands[pid][0]["cards"].append(self._draw())
            self.dealer.append(self._draw())
        # The dealer peeks: with a blackjack the hand ends before anyone acts.
        if is_blackjack(self.dealer):
            self._settle()
            return
        for pid in seats:
            hand = self.hands[pid][0]
            if is_blackjack(hand["cards"]):
                hand["done"] = True
        self.order = [(pid, 0) for pid in seats if not self.hands[pid][0]["done"]]
        self.turn = 0
        if not self.order:
            self._dealer_play()
            return
        self.phase = "play"
        self.set_deadline(self.timings["turn"])
        self.bump()

    def _place(self, pid: str, amount: int) -> None:
        self.chips[pid] -= amount
        self.bets[pid] = amount

    def _next_turn(self) -> None:
        self.turn += 1
        if self.turn >= len(self.order):
            self._dealer_play()
            return
        self.set_deadline(self.timings["turn"])
        self.bump()

    def _dealer_play(self) -> None:
        live = any(not self._bust(h) for hands in self.hands.values() for h in hands)
        if live:
            hits_soft = self.chaos == "soft17"
            while True:
                value, soft = hand_value(self.dealer)
                if value < 17 or (value == 17 and soft and hits_soft):
                    self.dealer.append(self._draw())
                else:
                    break  # stands on 17 (on soft 17 too, unless the Chaos card says otherwise)
        self._settle()

    @staticmethod
    def _bust(hand: dict[str, Any]) -> bool:
        return hand_value(hand["cards"])[0] > 21

    def _payout(self, hand: dict[str, Any], dealer_value: int, dealer_bj: bool) -> tuple[int, str]:
        value = hand_value(hand["cards"])[0]
        bet = hand["bet"]
        natural = is_blackjack(hand["cards"]) and not hand["split"]
        double = 2 if self.chaos == "double_pay" else 1
        if value > 21:
            return 0, "bust"
        if natural and not dealer_bj:
            return bet + bet * 3 // 2 * double, "blackjack"
        if dealer_bj and not natural:
            return 0, "lose"
        if natural and dealer_bj or value == dealer_value and dealer_value <= 21:
            return (bet * 2, "push") if self.chaos == "push_pays" else (bet, "push")
        if dealer_value > 21 or value > dealer_value:
            return bet + bet * double, "win"
        return 0, "lose"

    def _settle(self) -> None:
        dealer_value = hand_value(self.dealer)[0]
        dealer_bj = is_blackjack(self.dealer)
        main: dict[str, int] = {}
        outcomes: dict[str, list[str]] = {}
        for pid, hands in self.hands.items():
            total, outs = 0, []
            for h in hands:
                pay, out = self._payout(h, dealer_value, dealer_bj)
                self.chips[pid] += pay
                total += pay - h["bet"]
                outs.append(out)
            main[pid] = total
            outcomes[pid] = outs
        side: dict[str, dict[str, Any]] = {}
        for pid, s in self.side.items():
            target_net = main.get(s["on"], 0)
            pay = s["amount"] * 2 if target_net > 0 else s["amount"] if target_net == 0 else 0
            self.chips[pid] += pay
            side[pid] = {**s, "pay": pay}
        net: dict[str, int] = {}
        for pid in self.player_ids:
            if pid in main or pid in side:
                s = side.get(pid)
                net[pid] = main.get(pid, 0) + (s["pay"] - s["amount"] if s else 0)
        knocked = self._knockouts() if self.mode == "tournament" else []
        self.result = {
            "dealer": list(self.dealer),
            "dealer_value": dealer_value,
            "dealer_blackjack": dealer_bj,
            "net": net,
            "outcomes": outcomes,
            "side": side,
            "chaos": self.chaos,
            "eliminated": knocked,
        }
        self.history.append(
            {"hand": self.round + 1, "net": dict(net), "dealer_value": dealer_value, "chaos": self.chaos}
        )
        self.phase = "settle"
        self.set_deadline(self.timings["settle"])
        self.bump()

    def _knockouts(self) -> list[str]:
        """Tournament: the busted go out; from hand 2, so does the single shortest stack (ties are spared)."""
        knocked = [pid for pid in self.active if self.chips[pid] < BETS[0]]
        for pid in knocked:
            self.out.append({"player": pid, "hand": self.round + 1, "why": "busted"})
        left = [pid for pid in self.active if pid not in knocked]
        if self.round >= 1 and len(left) > 1:
            low = min(self.chips[p] for p in left)
            lowest = [p for p in left if self.chips[p] == low]
            if len(lowest) == 1:
                knocked.append(lowest[0])
                self.out.append({"player": lowest[0], "hand": self.round + 1, "why": "shortest stack"})
        self.active = [pid for pid in self.active if pid not in knocked]
        return knocked

    def _after_settle(self) -> None:
        over = self.round + 1 >= self.hands_total or (self.mode == "tournament" and len(self.active) <= 1)
        if over:
            self._finish_game()
        else:
            self.round += 1
            self._enter_bet()

    def _finish_game(self) -> None:
        if self.mode == "tournament":
            # Survivors by stack, then the knocked-out in reverse order (later out = better placed).
            alive = sorted(self.active, key=lambda p: -self.chips[p])
            gone = [o["player"] for o in reversed(self.out)]
            self.standings = alive + gone
            n = len(self.standings)
            for place, pid in enumerate(self.standings):
                bonus = CHAMPION_POINTS if place == 0 and len(alive) == 1 else 0
                self.round_scores[pid] = OUTLAST_POINTS * (n - 1 - place) + bonus
        else:
            self.standings = sorted(self.player_ids, key=lambda p: -self.chips[p])
            for pid in self.player_ids:
                self.round_scores[pid] = self.chips[pid] - START_CHIPS
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- actions ------------------------------------------------------------
    def _current(self) -> tuple[str, dict[str, Any]] | None:
        if self.phase != "play" or self.turn >= len(self.order):
            return None
        pid, i = self.order[self.turn]
        return pid, self.hands[pid][i]

    def actions_for(self, pid: str) -> list[str]:
        cur = self._current()
        if cur is None or cur[0] != pid:
            return []
        hand = cur[1]
        acts = ["hit", "stand"]
        two = len(hand["cards"]) == 2
        if two and not hand["doubled"] and self.chips[pid] >= hand["bet"]:
            acts.append("double")
        if (
            two
            and len(self.hands[pid]) == 1
            and card_value(hand["cards"][0]) == card_value(hand["cards"][1])
            and self.chips[pid] >= hand["bet"]
        ):
            acts.append("split")
        return acts

    def _bet(self, pid: str, action: dict[str, Any]) -> None:
        if self.phase != "bet":
            raise GameError("wrong_phase", "Bets are closed")
        if pid in self.bets:
            raise GameError("already_locked", "Your bet is already in")
        if pid not in self.active:
            raise GameError("eliminated", "You're out of this tournament")
        amount = as_int(action.get("amount"), lo=BETS[0], hi=BETS[-1], field="Bet")
        if amount not in BETS:
            raise GameError("bad_input", "Pick one of the chip sizes")
        side_on = action.get("side_on")
        side_amount = 0
        if side_on is not None:
            if not isinstance(side_on, str) or side_on == pid or side_on not in self._bettors():
                raise GameError("bad_input", "Back another player who's in this hand")
            side_amount = as_int(
                action.get("side_amount"), lo=SIDE_BETS[0], hi=SIDE_BETS[-1], field="Side bet"
            )
            if side_amount not in SIDE_BETS:
                raise GameError("bad_input", "Pick one of the side-bet sizes")
        if amount + side_amount > self.chips[pid]:
            raise GameError("bad_input", "You don't have that many chips")
        self._place(pid, amount)
        if side_on is not None:
            self.chips[pid] -= side_amount
            self.side[pid] = {"on": side_on, "amount": side_amount}
        self.bump()
        if all(b in self.bets for b in self._bettors()):
            self._deal()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "bet":
            self._bet(pid, action)
            return
        if kind not in ("hit", "stand", "double", "split"):
            raise GameError("bad_action", "Unknown action")
        if kind not in self.actions_for(pid):
            raise GameError("not_your_turn", "Not your move right now")
        cur = self._current()
        if cur is None:  # unreachable: actions_for already checked it's this player's turn
            raise GameError("not_your_turn", "Not your move right now")
        _, hand = cur
        if kind == "hit":
            hand["cards"].append(self._draw())
            if hand_value(hand["cards"])[0] >= 21:
                self._next_turn()
            else:
                self.set_deadline(self.timings["turn"])
                self.bump()
        elif kind == "stand":
            self._next_turn()
        elif kind == "double":
            self.chips[pid] -= hand["bet"]
            hand["bet"] *= 2
            hand["doubled"] = True
            hand["cards"].append(self._draw())
            self._next_turn()
        else:  # split
            self.chips[pid] -= hand["bet"]
            first, second = hand["cards"]
            aces = first.startswith("A")
            a = {
                "cards": [first, self._draw()],
                "bet": hand["bet"],
                "done": aces,
                "doubled": False,
                "split": True,
            }
            b = {
                "cards": [second, self._draw()],
                "bet": hand["bet"],
                "done": aces,
                "doubled": False,
                "split": True,
            }
            self.hands[pid] = [a, b]
            i = self.turn
            if aces:  # split aces: one card each, no more decisions
                self.order[i : i + 1] = []
                self.turn -= 1
                self._next_turn()
            else:
                self.order[i : i + 1] = [(pid, 0), (pid, 1)]
                self.set_deadline(self.timings["turn"])
                self.bump()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "bet":
            self._deal()
        elif self.phase == "play":
            self._next_turn()  # timer ran out: stand
        elif self.phase == "settle":
            self._after_settle()

    # -- views --------------------------------------------------------------
    def peek(self, pid: str) -> str | None:
        """Power card: the dealer's face-down card."""
        if self.phase != "play" or len(self.dealer) < 2:
            return None
        card = self.dealer[1]
        suit = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}[card[-1]]
        return f"The dealer's hidden card is {card[:-1]}{suit}."

    def view_for(self, pid: str) -> dict[str, Any]:
        show_dealer = self.phase in ("settle", "final")
        dealer_cards = list(self.dealer) if show_dealer else self.dealer[:1]
        cur = self._current()
        chaos = self.chaos if self.phase != "final" else None
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.hands_total,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "mode": self.mode,
            "active": list(self.active),
            "out": [dict(o) for o in self.out],
            "chips": dict(self.chips),
            "bets": dict(self.bets),
            "side": {k: dict(v) for k, v in self.side.items()},  # side bets are on the table: public
            "bet_sizes": list(BETS),
            "side_sizes": list(SIDE_BETS) if len(self.players) > 1 else [],
            # The Chaos card is only announced when its hand opens; until then just that one is coming.
            "chaos": {"id": chaos, **CHAOS[chaos]} if chaos else None,
            "chaos_coming": self.round < self.chaos_hand and self.phase != "final",
            "hands": {
                p: [
                    {
                        "cards": list(h["cards"]),
                        "bet": h["bet"],
                        "value": hand_value(h["cards"])[0],
                        "soft": hand_value(h["cards"])[1],
                    }
                    for h in hands
                ]
                for p, hands in self.hands.items()
            },
            # Only the up card until the dealer plays; the hole card and the shoe stay on the server.
            "dealer": {
                "cards": dealer_cards,
                "hidden": not show_dealer and len(self.dealer) > 1,
                "value": hand_value(dealer_cards)[0] if dealer_cards else 0,
            },
            "shoe_left": len(self.shoe),
            "reshuffled": self.reshuffled,
            "turn": {"player": cur[0], "hand": self.order[self.turn][1]} if cur else None,
            "you": {"actions": self.actions_for(pid), "bet": self.bets.get(pid)},
        }
        if self.phase == "settle" and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = self.history
            view["standings"] = list(self.standings)
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished or not self.history:
            return []
        out: list[dict[str, str]] = []
        best = max(
            ((pid, n, h["hand"]) for h in self.history for pid, n in h["net"].items()),
            key=lambda x: x[1],
            default=None,
        )
        if best and best[1] > 0:
            text = f"{self.name_of(best[0])} won {best[1]} chips on hand {best[2]}"
            out.append({"icon": "💰", "title": "Biggest pot", "text": text})
        if self.mode == "tournament" and self.standings:
            champ = self.standings[0]
            if len(self.active) == 1:
                out.append(
                    {
                        "icon": "🏆",
                        "title": "Last one standing",
                        "text": f"{self.name_of(champ)} outlasted the table",
                    }
                )
        elif self.standings:
            top = self.standings[0]
            if self.chips[top] > START_CHIPS:
                text = f"{self.name_of(top)} cashed out with {self.chips[top]} chips"
                out.append({"icon": "🃏", "title": "High roller", "text": text})
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "hands": len(self.history), "mode": self.mode}
