"""Blackjack Showdown: the whole room at one table against the dealer.

Five hands, 1,000 chips each, bets of 50/100/200/500. Six-deck shoe (reshuffled when it runs low),
dealer peeks for blackjack and stands on soft 17, blackjack pays 3:2. Hit, stand, double on the first
two cards, one split per hand (split aces get one card each). Every phase and turn has a timer: a
missed bet auto-bets the minimum, a missed turn stands. Your game score is your net chips.

Secrecy: the dealer's hole card and the shoe order exist only here until the dealer plays.
Everyone's own cards are face up, as at a real table.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]
BETS = (50, 100, 200, 500)
START_CHIPS = 1000
DECKS = 6


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
        "The whole room at one table against the dealer. Five hands, 1,000 chips each: "
        "hit, stand, double down, split. Biggest stack wins."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    HANDS = 5

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"bet": 25.0, "turn": 25.0, "settle": 9.0}

    # -- setup --------------------------------------------------------------
    def start(self) -> None:
        self.chips: dict[str, int] = {p.id: START_CHIPS for p in self.players}
        self.shoe: list[str] = []
        self._reshuffle()
        self.round = 0
        self.history: list[dict[str, Any]] = []
        self._enter_bet()

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
        self.hands: dict[str, list[dict[str, Any]]] = {}
        self.dealer: list[str] = []
        self.order: list[tuple[str, int]] = []
        self.turn = 0
        self.result: dict[str, Any] | None = None
        self.phase = "bet"
        self.set_deadline(self.timings["bet"])
        self.bump()
        if not self._bettors():
            self._finish_game()

    def _bettors(self) -> list[str]:
        return [pid for pid in self.player_ids if self.chips[pid] >= BETS[0]]

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
            while True:
                value, soft = hand_value(self.dealer)
                if value < 17:
                    self.dealer.append(self._draw())
                else:
                    break  # stands on 17, soft 17 included
        self._settle()

    @staticmethod
    def _bust(hand: dict[str, Any]) -> bool:
        return hand_value(hand["cards"])[0] > 21

    def _settle(self) -> None:
        dealer_value = hand_value(self.dealer)[0]
        dealer_bj = is_blackjack(self.dealer)
        net: dict[str, int] = {}
        outcomes: dict[str, list[str]] = {}
        for pid, hands in self.hands.items():
            total = 0
            outs = []
            for h in hands:
                value = hand_value(h["cards"])[0]
                natural = is_blackjack(h["cards"]) and not h["split"]
                if value > 21:
                    pay, out = 0, "bust"
                elif natural and not dealer_bj:
                    pay, out = h["bet"] + h["bet"] * 3 // 2, "blackjack"
                elif dealer_bj and not natural:
                    pay, out = 0, "lose"
                elif natural and dealer_bj or value == dealer_value and dealer_value <= 21:
                    pay, out = h["bet"], "push"
                elif dealer_value > 21 or value > dealer_value:
                    pay, out = h["bet"] * 2, "win"
                else:
                    pay, out = 0, "lose"
                self.chips[pid] += pay
                total += pay - h["bet"]
                outs.append(out)
            net[pid] = total
            outcomes[pid] = outs
        self.result = {
            "dealer": list(self.dealer),
            "dealer_value": dealer_value,
            "dealer_blackjack": dealer_bj,
            "net": net,
            "outcomes": outcomes,
        }
        self.history.append({"hand": self.round + 1, "net": dict(net), "dealer_value": dealer_value})
        self.phase = "settle"
        self.set_deadline(self.timings["settle"])
        self.bump()

    def _after_settle(self) -> None:
        if self.round + 1 >= self.HANDS:
            self._finish_game()
        else:
            self.round += 1
            self._enter_bet()

    def _finish_game(self) -> None:
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

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "bet":
            if self.phase != "bet":
                raise GameError("wrong_phase", "Bets are closed")
            if pid in self.bets:
                raise GameError("already_locked", "Your bet is already in")
            amount = as_int(action.get("amount"), lo=BETS[0], hi=BETS[-1], field="Bet")
            if amount not in BETS:
                raise GameError("bad_input", "Pick one of the chip sizes")
            if amount > self.chips[pid]:
                raise GameError("bad_input", "You don't have that many chips")
            self._place(pid, amount)
            self.bump()
            if all(b in self.bets for b in self._bettors()):
                self._deal()
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
    def view_for(self, pid: str) -> dict[str, Any]:
        show_dealer = self.phase in ("settle", "final")
        dealer_cards = list(self.dealer) if show_dealer else self.dealer[:1]
        cur = self._current()
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.HANDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "chips": dict(self.chips),
            "bets": dict(self.bets),
            "bet_sizes": list(BETS),
            "hands": {
                p: [
                    {"cards": list(h["cards"]), "bet": h["bet"], "value": hand_value(h["cards"])[0]}
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
        return view

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "hands": len(self.history)}
