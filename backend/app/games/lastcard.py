"""Last Card: the classic shedding card game (Uno rules), our name.

Deck: 108 cards. Four colours, each with one 0, two of 1-9 and two each of Skip, Reverse and Draw Two;
plus four Wilds and four Wild Draw Fours. Seven cards each; the top of the pile is turned over (a Wild
Draw Four, or a plain Wild, goes back and another is turned: the house has no dealer to pick a colour).
An action card turned at the start works on the first player as if the dealer had played it.

Your turn: play a card matching the colour, number or symbol on the pile, or any Wild (you name the
colour). Or draw one card; if it can be played you may play it straight away, otherwise your turn ends.
Skip: the next player misses a turn. Reverse: direction changes (with two players it works as a Skip).
Draw Two: the next player draws two and misses their turn. Wild Draw Four: next player draws four and
misses their turn, but you may only play it when you hold no card of the current colour, and the next
player may challenge: if you played it illegally you draw the four instead; if not, they draw six.

Stacking (an option, off by default as in the official rules): a Draw Two may be answered with another
Draw Two, a Wild Draw Four with another Wild Draw Four; the total lands on whoever can't (or won't) add.

Last card: when you play your second-to-last card, tap LAST CARD (on your turn with two cards, or right
after). If anyone catches you with one card before the next player acts, you draw two.

The hand ends when someone plays their last card (a final Draw Two or Draw Four is still drawn). They
score every card left in the others' hands: number cards at face value, action cards 20, Wilds 50.
1 or 3 hands. A 30-second turn clock keeps the party moving: time out and you draw.

Teams (the official partner rule): partners sit opposite each other; when anyone goes out, their team
wins the hand and scores only the cards left in the other team's hands.

Secrecy: your hand and the draw pile are yours and the server's alone; everyone sees how many cards each
player holds. Whether a Wild Draw Four was legal stays hidden until it is challenged. Hands are shown to
everyone once the hand is over.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

COLORS = ("red", "yellow", "green", "blue")
ACTIONS = ("skip", "reverse", "draw2")
HAND = 7
TURN_SECONDS = 30.0
CATCH_PENALTY = 2


def build_deck() -> list[tuple[str, str]]:
    """Card id -> (colour, value). Colour "wild" for Wild and Wild Draw Four."""
    cards: list[tuple[str, str]] = []
    for c in COLORS:
        cards.append((c, "0"))
        for v in [*(str(n) for n in range(1, 10)), *ACTIONS]:
            cards += [(c, v), (c, v)]
    cards += [("wild", "wild")] * 4 + [("wild", "wild4")] * 4
    return cards


CARDS = build_deck()


def card_points(card: int) -> int:
    _, value = CARDS[card]
    if value.isdigit():
        return int(value)
    return 50 if value in ("wild", "wild4") else 20


class LastCard(Game):
    game_id: ClassVar[str] = "lastcard"
    title: ClassVar[str] = "Last Card"
    blurb: ClassVar[str] = (
        "The colour-matching card game everyone knows: skips, reverses, draw twos and wild draw fours. "
        "Down to one card? Shout it before they catch you."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"hands": ["1", "3"], "stacking": ["off", "on"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Match the top card by colour, number or symbol, or play a Wild and pick the colour.",
        "Can't (or won't) play? Draw one. If it fits, you may play it straight away.",
        "Skip, Reverse and Draw Two hit the next player. Wild Draw Four only when you have nothing "
        "of the current colour, and it can be challenged.",
        "Down to one card? Tap LAST CARD! Anyone who catches you first makes you draw two.",
        "First to empty their hand scores everyone else's cards: numbers at face value, actions 20, "
        "wilds 50.",
    )
    READING: ClassVar[frozenset[str]] = frozenset({"hand_over"})

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"turn": TURN_SECONDS, "hand_over": 15.0}

    # -- setup ----------------------------------------------------------------------------------------
    def start(self) -> None:
        self.hands_total = 3 if self.options.get("hands") == "3" else 1
        self.stacking = self.options.get("stacking") == "on"
        self.order: list[str] = list(self.player_ids)
        self.rng.shuffle(self.order)
        if self.teams:  # partners sit opposite: the seats alternate between the teams
            sides = [[p for p in self.order if self.teams.get(p) == t] for t in (0, 1)]
            self.order = [p for pair in zip(*sides, strict=False) for p in pair]
            self.order += [p for side in sides for p in side[min(map(len, sides)) :]]
        self.hand_no = 0
        self.history: list[dict[str, Any]] = []
        self.stats: dict[str, dict[str, int]] = {
            p: {"wild4": 0, "caught": 0, "biggest_draw": 0, "won": 0} for p in self.player_ids
        }
        self._deal()

    def _deal(self) -> None:
        self.deck: list[int] = list(range(len(CARDS)))
        self.rng.shuffle(self.deck)
        self.discard: list[int] = []
        self.hands: dict[str, list[int]] = {p: [] for p in self.order}
        for _ in range(HAND):
            for p in self.order:
                self.hands[p].append(self.deck.pop())
        self.direction = 1
        self.pending: dict[str, Any] | None = None  # a draw waiting for its victim
        self.drawn: int | None = None  # the card the current player just drew (they may play it)
        self.protected: set[str] = set()  # called LAST CARD
        self.vulnerable: set[str] = set()  # on one card, didn't call, can still be caught
        self.log: list[dict[str, Any]] = []
        self.winner: str | None = None
        # The dealer moves round each hand; the player after them starts.
        dealer = (self.hand_no - 1) % len(self.order)
        self.turn = dealer
        while True:  # turn a starter: wilds go back in (there's no dealer to choose a colour)
            card = self.deck.pop()
            if CARDS[card][0] != "wild":
                break
            self.deck.insert(0, card)
        self.discard.append(card)
        self.color = CARDS[card][0]
        self.log.append({"type": "start", "card": card, "base": CARDS[card][0], "value": CARDS[card][1]})
        self.phase = "play"
        self._resolve_start(card)
        self.bump()

    def _resolve_start(self, card: int) -> None:
        """The turned card acts on the first player, as if the dealer had played it."""
        value = CARDS[card][1]
        if value == "reverse" and len(self.order) > 2:
            self.direction = -1
            self._next(0)  # the dealer's other neighbour starts
            return
        self._next(0)
        if value == "skip" or (value == "reverse" and len(self.order) == 2):
            self.log.append({"type": "skipped", "player": self.current})
            self._next(0)
        elif value == "draw2":
            self._give(self.current, 2, reason="draw2")
            self._next(0)

    # -- helpers --------------------------------------------------------------------------------------
    @property
    def current(self) -> str:
        return self.order[self.turn]

    def _next(self, skip: int) -> None:
        self.turn = (self.turn + self.direction * (1 + skip)) % len(self.order)
        self.drawn = None
        self.set_deadline(self.timings["turn"])

    def _top(self) -> int:
        return self.discard[-1]

    def _draw_one(self) -> int | None:
        if not self.deck and len(self.discard) > 1:
            top = self.discard.pop()
            self.deck = self.discard
            self.rng.shuffle(self.deck)
            self.discard = [top]
            self.log.append({"type": "reshuffle"})
        return self.deck.pop() if self.deck else None

    def _give(self, pid: str, n: int, reason: str) -> int:
        got = 0
        for _ in range(n):
            card = self._draw_one()
            if card is None:
                break
            self.hands[pid].append(card)
            got += 1
        if len(self.hands[pid]) > 1:
            self.protected.discard(pid)
            self.vulnerable.discard(pid)
        if got:
            self.log.append({"type": "draw", "player": pid, "n": got, "reason": reason})
            s = self.stats[pid]
            s["biggest_draw"] = max(s["biggest_draw"], got)
        return got

    def playable(self, pid: str, card: int) -> bool:
        color, value = CARDS[card]
        if self.pending is not None:
            # Only stacking answers a waiting draw.
            want = "draw2" if self.pending["kind"] == "draw2" else "wild4"
            return self.stacking and value == want
        if self.drawn is not None and card != self.drawn:
            return False
        if color == "wild":
            return True
        top_color, top_value = CARDS[self._top()]
        return color == self.color or value == top_value

    def chat_team(self, pid: str) -> tuple[str, str] | None:
        """No private partner chat: talking about your hands is against the rules."""
        return None

    def _partners(self, a: str, b: str) -> bool:
        return bool(self.teams) and self.teams.get(a) == self.teams.get(b)

    def _actor(self, pid: str) -> None:
        if self.phase != "play":
            raise GameError("wrong_phase", "Wait for the next hand")
        if pid != self.current:
            raise GameError("not_your_turn", "It's not your turn")

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "play":
            self._play(pid, action)
        elif kind == "draw":
            self._draw(pid)
        elif kind == "pass":
            self._pass(pid)
        elif kind == "challenge":
            self._challenge(pid)
        elif kind == "last":
            self._call_last(pid)
        elif kind == "catch":
            self._catch(pid, action)
        else:
            raise GameError("bad_action", "Unknown action")
        if kind in ("play", "draw", "pass", "challenge"):
            # A move by the next player closes the window for catching whoever went before.
            self.vulnerable = {p for p in self.vulnerable if p == pid}
        self.bump()

    def _play(self, pid: str, action: dict[str, Any]) -> None:
        self._actor(pid)
        card = as_int(action.get("card"), lo=0, hi=len(CARDS) - 1, field="Card")
        hand = self.hands[pid]
        if card not in hand:
            raise GameError("not_your_card", "That card isn't in your hand")
        if not self.playable(pid, card):
            raise GameError("cant_play", "That card doesn't match")
        color, value = CARDS[card]
        if color == "wild":
            chosen = action.get("color")
            if chosen not in COLORS:
                raise GameError("bad_input", "Pick a colour")
            color = chosen
        legal_wild4 = value != "wild4" or not any(CARDS[c][0] == self.color for c in hand if c != card)
        hand.remove(card)
        self.discard.append(card)
        was = self.color
        self.color = color
        # Played cards are public: name them, so every screen can say (and show) what was played.
        self.log.append(
            {
                "type": "play",
                "player": pid,
                "card": card,
                "base": CARDS[card][0],
                "value": value,
                "color": color,
            }
        )
        if value == "wild4":
            self.stats[pid]["wild4"] += 1
        if len(hand) == 1 and pid not in self.protected:
            self.vulnerable.add(pid)
        if not hand:
            self._finish_hand(pid, value)
            return
        self._effect(pid, value, legal_wild4, was)

    def _effect(self, pid: str, value: str, legal_wild4: bool, was: str) -> None:
        n = len(self.order)
        if value == "skip" or (value == "reverse" and n == 2):
            self._next(0)
            self.log.append({"type": "skipped", "player": self.current})
            self._next(0)
        elif value == "reverse":
            self.direction = -self.direction
            self.log.append({"type": "reverse", "direction": self.direction})
            self._next(0)
        elif value == "draw2":
            stacked = self.pending["n"] if self.pending else 0
            self.pending = {"kind": "draw2", "n": stacked + 2, "by": pid}
            self._next(0)
            if not self.stacking:
                self._take_pending()
        elif value == "wild4":
            stacked = self.pending["n"] if self.pending else 0
            # "was": the colour they had to match (what a challenge asks about); public, unlike "legal".
            self.pending = {"kind": "wild4", "n": stacked + 4, "by": pid, "legal": legal_wild4, "was": was}
            self._next(0)
        else:
            self.pending = None
            self._next(0)

    def _take_pending(self) -> None:
        """The current player draws the waiting total and misses their turn."""
        if self.pending is None:
            return
        victim = self.current
        self._give(victim, self.pending["n"], reason=self.pending["kind"])
        self.pending = None
        self._next(0)

    def _draw(self, pid: str) -> None:
        self._actor(pid)
        if self.pending is not None:
            self._take_pending()
            return
        if self.drawn is not None:
            raise GameError("already_drew", "You've drawn: play it or pass")
        card = self._draw_one()
        if card is None:  # nothing left anywhere: just pass
            self._next(0)
            return
        self.hands[pid].append(card)
        self.protected.discard(pid)
        self.log.append({"type": "draw", "player": pid, "n": 1, "reason": "draw"})
        if self.playable(pid, card):
            self.drawn = card  # play it now, or pass
        else:
            self._next(0)

    def _pass(self, pid: str) -> None:
        self._actor(pid)
        if self.drawn is None:
            raise GameError("draw_first", "Draw a card first")
        self.log.append({"type": "pass", "player": pid})
        self._next(0)

    def _challenge(self, pid: str) -> None:
        self._actor(pid)
        p = self.pending
        if p is None or p["kind"] != "wild4":
            raise GameError("nothing_to_challenge", "There's nothing to challenge")
        offender = p["by"]
        if not p["legal"]:
            # Caught: the player who bluffed draws the four, and the challenger plays on.
            self.log.append({"type": "challenge", "player": pid, "against": offender, "won": True})
            self._give(offender, p["n"], reason="challenge")
            self.pending = None
            self.set_deadline(self.timings["turn"])
        else:
            self.log.append({"type": "challenge", "player": pid, "against": offender, "won": False})
            self.pending = {**p, "n": p["n"] + 2}
            self._take_pending()

    def _call_last(self, pid: str) -> None:
        if self.phase != "play":
            raise GameError("wrong_phase", "Wait for the next hand")
        n = len(self.hands[pid])
        if pid in self.protected:
            raise GameError("already_called", "You've already called it")
        if not ((n == 2 and pid == self.current) or (n == 1 and pid in self.vulnerable)):
            raise GameError("too_early", "Only when you're about to have one card left")
        self.protected.add(pid)
        self.vulnerable.discard(pid)
        self.log.append({"type": "last", "player": pid})

    def _catch(self, pid: str, action: dict[str, Any]) -> None:
        if self.phase != "play":
            raise GameError("wrong_phase", "Wait for the next hand")
        target = action.get("target")
        if not isinstance(target, str) or target == pid or target not in self.vulnerable:
            raise GameError("no_catch", "Too late: nobody to catch")
        self.vulnerable.discard(target)
        self.stats[target]["caught"] += 1
        self.log.append({"type": "caught", "player": target, "by": pid})
        self._give(target, CATCH_PENALTY, reason="caught")

    # -- the end of a hand ----------------------------------------------------------------------------
    def _finish_hand(self, winner: str, last_value: str) -> None:
        # A final Draw Two / Draw Four still lands on the next player (and counts for the winner).
        if last_value in ("draw2", "wild4"):
            self._next(0)
            self._give(self.current, 2 if last_value == "draw2" else 4, reason=last_value)
        rivals = [p for p in self.hands if p != winner and not self._partners(p, winner)]
        points = sum(card_points(c) for p in rivals for c in self.hands[p])
        self.add_points(winner, points)
        self.stats[winner]["won"] += 1
        self.winner = winner
        self.pending = None
        self.vulnerable.clear()
        self.history.append(
            {"winner": winner, "points": points, "left": {p: len(h) for p, h in self.hands.items()}}
        )
        self.log.append({"type": "win", "player": winner, "points": points})
        self.phase = "hand_over"
        self.set_deadline(self.timings["hand_over"])

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()
            self.bump()

    def advance(self) -> None:
        """Timer or host. A silent turn draws (and passes); the hand-over screen moves on."""
        if self.finished:
            return
        if self.phase == "play":
            pid = self.current
            self.log.append({"type": "timeout", "player": pid})
            if self.pending is not None:
                self._take_pending()
            elif self.drawn is not None:
                self._next(0)
            else:
                self._draw(pid)
                if self.drawn is not None:
                    self._next(0)  # out of time: keep the card, turn over
        elif self.phase == "hand_over":
            self.hand_no += 1
            if self.hand_no >= self.hands_total:
                self.phase = "final"
                self.deadline = None
                self.finished = True
            else:
                self._deal()
        self.bump()

    # -- views ----------------------------------------------------------------------------------------
    @staticmethod
    def _card(card: int) -> dict[str, Any]:
        color, value = CARDS[card]
        return {"id": card, "color": color, "value": value}

    def view_for(self, pid: str) -> dict[str, Any]:
        playing = self.phase == "play"
        open_book = self.phase in ("hand_over", "final")
        mine = self.hands.get(pid)
        my_turn = playing and pid == self.current
        pending = None
        if self.pending is not None:
            pending = {k: v for k, v in self.pending.items() if k != "legal"}  # legality is secret
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": min(self.hand_no, self.hands_total - 1) + 1,
            "rounds": self.hands_total,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "order": list(self.order),
            "turn": self.current if playing else None,
            "direction": self.direction,
            "top": self._card(self._top()),
            "color": self.color,
            "pending": pending,
            "stacking": self.stacking,
            "counts": {p: len(h) for p, h in self.hands.items()},
            "deck": len(self.deck),
            "protected": sorted(self.protected),
            "vulnerable": sorted(self.vulnerable) if playing else [],
            "log": self.log[-14:],
            "you": None,
            "winner": self.winner if open_book else None,
            "scores": {
                p: sum(h["points"] for h in self.history if h["winner"] == p) for p in self.player_ids
            },
        }
        if mine is not None:
            view["you"] = {
                "hand": [{**self._card(c), "playable": my_turn and self.playable(pid, c)} for c in mine],
                "drawn": self.drawn if my_turn else None,
                "can_last": playing
                and pid not in self.protected
                and ((len(mine) == 2 and my_turn) or (len(mine) == 1 and pid in self.vulnerable)),
            }
        if open_book:
            view["hands"] = {p: [self._card(c) for c in h] for p, h in self.hands.items()}
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        best = max(self.history, key=lambda h: h["points"], default=None)
        if best:
            out.append(
                {
                    "icon": "🃏",
                    "title": "Cleaned out",
                    "text": f"{self.name_of(best['winner'])} went out for {best['points']} points",
                }
            )
        bandit = max(self.player_ids, key=lambda p: self.stats[p]["wild4"])
        if self.stats[bandit]["wild4"] >= 2:
            out.append(
                {
                    "icon": "😈",
                    "title": "Draw-four bandit",
                    "text": f"{self.name_of(bandit)} played {self.stats[bandit]['wild4']} Wild Draw Fours",
                }
            )
        caught = max(self.player_ids, key=lambda p: self.stats[p]["caught"])
        if self.stats[caught]["caught"]:
            out.append(
                {
                    "icon": "🚨",
                    "title": "Caught napping",
                    "text": f"{self.name_of(caught)} forgot to call LAST CARD",
                }
            )
        big = max(self.player_ids, key=lambda p: self.stats[p]["biggest_draw"])
        if self.stats[big]["biggest_draw"] >= 6:
            out.append(
                {
                    "icon": "📚",
                    "title": "Bookworm",
                    "text": f"{self.name_of(big)} picked up {self.stats[big]['biggest_draw']} in one go",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "hands": len(self.history), "stacking": self.stacking}
