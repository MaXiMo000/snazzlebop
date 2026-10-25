"""Five Dice (Yahtzee rules, our own name): roll, hold, roll again, fill your scorecard.

Everyone plays their own card at the same time, so a room of eight takes no longer than two. Each round
you roll five dice up to three times, holding any between rolls, then score them in one empty box of
your card. Thirteen rounds fill the thirteen boxes:
- Ones to Sixes: the total of that number. 63 or more across them earns a 35 bonus.
- Three / Four of a Kind: the total of all dice. Full House 25, Small Straight (four in a row) 30,
  Large Straight (five) 40, Five Dice (all the same) 50, Chance: the total of all dice.
- Another Five Dice when that box already holds 50 is a 100 bonus, and the joker rules apply: fill
  the matching upper box if it's empty, otherwise any lower box (Full House and the straights score in
  full), otherwise zero an upper box.
A round clock rolls (if needed) and fills the best box for anyone who's away. Nothing is secret.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from .base import Game, GameError

UPPER = ("ones", "twos", "threes", "fours", "fives", "sixes")
LOWER = ("three_kind", "four_kind", "full_house", "small_straight", "large_straight", "five_dice", "chance")
BOXES = UPPER + LOWER
UPPER_BONUS, UPPER_NEEDS = 35, 63
FIVE_BONUS = 100
ROLLS = 3


def box_score(box: str, dice: list[int], joker: bool = False) -> int:
    """What these dice score in a box (joker: a Five Dice standing in for FH or a straight)."""
    counts = Counter(dice)
    total = sum(dice)
    if box in UPPER:
        face = UPPER.index(box) + 1
        return face * counts[face]
    if box == "three_kind":
        return total if max(counts.values()) >= 3 else 0
    if box == "four_kind":
        return total if max(counts.values()) >= 4 else 0
    if box == "full_house":
        return 25 if joker or sorted(counts.values()) == [2, 3] else 0
    if box == "small_straight":
        faces = set(dice)
        return 30 if joker or any({s, s + 1, s + 2, s + 3} <= faces for s in (1, 2, 3)) else 0
    if box == "large_straight":
        return 40 if joker or set(dice) in ({1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}) else 0
    if box == "five_dice":
        return 50 if len(counts) == 1 else 0
    return total  # chance


class Card:
    """One player's dice and scorecard."""

    def __init__(self) -> None:
        self.boxes: dict[str, int] = {}
        self.dice: list[int] = [0] * 5
        self.held: list[bool] = [False] * 5
        self.rolls = 0
        self.extra = 0  # extra rolls this round (a power-up)
        self.bonus = 0  # Five Dice bonuses
        self.done = False  # scored this round

    @property
    def upper(self) -> int:
        return sum(self.boxes.get(b, 0) for b in UPPER)

    @property
    def total(self) -> int:
        return sum(self.boxes.values()) + (UPPER_BONUS if self.upper >= UPPER_NEEDS else 0) + self.bonus

    def allowed(self) -> dict[str, int]:
        """The boxes these dice may go in, with what each would score (the joker rules included)."""
        if not self.rolls:
            return {}
        open_boxes = [b for b in BOXES if b not in self.boxes]
        five = len(set(self.dice)) == 1 and "five_dice" in self.boxes
        if five:
            mine = UPPER[self.dice[0] - 1]
            if mine not in self.boxes:
                return {mine: box_score(mine, self.dice)}
            lower = [b for b in LOWER if b not in self.boxes]
            if lower:
                return {b: box_score(b, self.dice, joker=True) for b in lower}
            return {b: 0 for b in open_boxes}
        return {b: box_score(b, self.dice) for b in open_boxes}


class FiveDice(Game):
    game_id: ClassVar[str] = "fivedice"
    title: ClassVar[str] = "Five Dice"
    blurb: ClassVar[str] = (
        "Roll five dice three times, hold the ones you like, fill your scorecard. Straights, full houses "
        "and the dream: five of a kind. Everyone plays at once."
    )
    min_players: ClassVar[int] = 1
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"card": ["13", "7"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone plays their own scorecard at the same time.",
        "Each round: roll up to three times, tapping dice to hold them between rolls.",
        "Then score in one empty box. Ones to Sixes: 63+ earns a 35 bonus.",
        "Full House 25, straights 30 and 40, five of a kind 50 (and 100 more for each one after that).",
    )

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"round": 75.0}

    def start(self) -> None:
        self.rounds = int(self.options.get("card", "13"))
        self.cards = {p: Card() for p in self.player_ids}
        self.log: list[dict[str, Any]] = []
        self.round = 0
        self._begin()

    def _begin(self) -> None:
        for c in self.cards.values():
            c.dice, c.held, c.rolls, c.done, c.extra = [0] * 5, [False] * 5, 0, False, 0
        self.phase = "play"
        self.set_deadline(self.timings["round"])
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if self.phase != "play":
            raise GameError("wrong_phase", "The game is over")
        card = self.cards[pid]
        if card.done:
            raise GameError("done", "You've scored this round: wait for the others")
        kind = action.get("a")
        if kind == "roll":
            self._roll(card, action.get("held"))
        elif kind == "score":
            box = action.get("box")
            if not isinstance(box, str) or box not in BOXES:
                raise GameError("bad_input", "Which box?")
            self._score(pid, box)
        else:
            raise GameError("bad_action", "Unknown action")

    POWERS: ClassVar[dict[str, dict[str, str]]] = {
        "fivedice_roll": {"name": "Extra roll", "icon": "🎲", "text": "A fourth roll this round"},
    }

    def use_power(self, pid: str, item: str) -> str | None:
        if item != "fivedice_roll":
            return super().use_power(pid, item)
        card = self.cards.get(pid)
        if self.phase != "play" or card is None or card.done:
            raise GameError("wrong_phase", "Use it before you score this round")
        if card.extra:
            raise GameError("not_now", "You've an extra roll already")
        card.extra = 1
        self.bump()
        return "You get a fourth roll this round."

    def _roll(self, card: Card, held: Any) -> None:
        if card.rolls >= ROLLS + card.extra:
            raise GameError("no_rolls", "That was your last roll: pick a box")
        if card.rolls == 0:
            card.held = [False] * 5
        else:
            if not isinstance(held, list) or len(held) != 5 or not all(isinstance(h, bool) for h in held):
                raise GameError("bad_input", "Which dice are you holding?")
            card.held = list(held)
        card.dice = [d if h else self.rng.randint(1, 6) for d, h in zip(card.dice, card.held, strict=True)]
        card.rolls += 1
        self.bump()

    def _score(self, pid: str, box: str) -> None:
        card = self.cards[pid]
        options = card.allowed()
        if not options:
            raise GameError("roll_first", "Roll first")
        if box not in options:
            raise GameError("bad_box", "You can't score these dice there")
        before = card.total
        if len(set(card.dice)) == 1 and card.boxes.get("five_dice") == 50:
            card.bonus += FIVE_BONUS
        card.boxes[box] = options[box]
        card.done = True
        self.add_points(pid, card.total - before)
        self.log.append(
            {"by": pid, "box": box, "points": options[box], "dice": list(card.dice), "round": self.round}
        )
        self.bump()
        if all(c.done for c in self.cards.values()):
            self._next()

    def _next(self) -> None:
        if self.round + 1 >= self.rounds:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.round += 1
        self._begin()

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        """The round clock ran out: roll for anyone who hasn't, and fill their best box."""
        if self.finished:
            return
        this_round = self.round
        for pid, card in list(self.cards.items()):
            if self.finished or self.round != this_round:
                break  # the last box filled ended the round: the next one starts fresh
            if card.done:
                continue
            if not card.rolls:
                self._roll(card, None)
            options = card.allowed()
            best = max(options, key=lambda b: (options[b], -BOXES.index(b)))
            self._score(pid, best)

    def skip(self) -> bool:
        """Never: it would fill a box for whoever is still deciding (the round clock does that)."""
        return False

    # -- views ----------------------------------------------------------------------------------------
    def _card_view(self, card: Card) -> dict[str, Any]:
        return {
            "boxes": dict(card.boxes),
            "dice": list(card.dice),
            "held": list(card.held),
            "rolls": card.rolls,
            "max_rolls": ROLLS + card.extra,
            "done": card.done,
            "upper": card.upper,
            "bonus": card.bonus,
            "total": card.total,
        }

    def view_for(self, pid: str) -> dict[str, Any]:
        mine = self.cards.get(pid)
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "cards": {p: self._card_view(c) for p, c in self.cards.items()},
            "scores": self.scores(),
            "you": {"options": mine.allowed() if not mine.done else {}} if mine is not None else None,
            "last": self.log[-8:],
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        fives = [e for e in self.log if e["box"] == "five_dice" and e["points"] == 50]
        if fives:
            out.append(
                {
                    "icon": "🎲",
                    "title": "Five of a kind!",
                    "text": f"{self.name_of(fives[0]['by'])} rolled five {fives[0]['dice'][0]}s",
                }
            )
        bonus = [p for p, c in self.cards.items() if c.upper >= UPPER_NEEDS]
        if bonus:
            out.append(
                {"icon": "⭐", "title": "Upper bonus", "text": f"{self.name_of(bonus[0])} made 63 up top"}
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": self.round + 1}
