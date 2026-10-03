"""Wager Wits: you don't have to know the answer, just who does.

Each round asks a question with a whole-number answer. Everyone answers in secret. The answers go up
on a board, sorted, with a "lower than all of them" slot in front. Then everyone places two free
chips on whichever answers they think are closest *without going over*. Odds grow from 2:1 in the
middle of the board to 5:1 at the edges; "lower than all" pays 6:1. Each chip on the winning slot
pays 100 x its odds, and whoever wrote the winning answer gets +100. Six rounds.

The last question is ALL IN: instead of free chips, everyone wagers their own points on one slot (up
to everything they've won this game, or 200 if that's less). Right: the wager times the odds. Wrong:
the wager is gone.

Secrecy: answers stay hidden until everyone has answered (then they're the board); bets stay
hidden until the reveal; the true answer only arrives with the reveal.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import WITS_QUESTIONS

ROUNDS = 6
CHIPS = 2
CHIP_VALUE = 100
AUTHOR_BONUS = 100
TOO_LOW_ODDS = 6
MAX_ANSWER = 10**9
ALL_IN_FLOOR = 200  # the most you can wager when you have less than this


def board_odds(n: int) -> list[int]:
    """Odds for slot 0 ("lower than all") and the n sorted answers: 2:1 in the middle, up to 5:1."""
    mid = (n - 1) / 2
    return [TOO_LOW_ODDS] + [min(5, 2 + int(abs(i - mid))) for i in range(n)]


class WagerWits(Game):
    game_id: ClassVar[str] = "wits"
    title: ClassVar[str] = "Wager Wits"
    blurb: ClassVar[str] = (
        "A question with a number for an answer. Everyone guesses, then bets on whose guess is closest "
        "without going over. You can win without knowing a thing."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "A question with a number for an answer. Everyone writes a guess.",
        "The guesses go on a board. Bet your 2 free chips on the one closest WITHOUT going over "
        "(your own counts too).",
        "Odds are bigger at the edges of the board. Writing the winning guess: +100.",
        "The last question is ALL IN: bet your own points on one answer.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["reveal"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"answer": 45.0, "bet": 35.0, "reveal": 15.0}

    def start(self) -> None:
        self.questions = [
            WITS_QUESTIONS[i] for i in self.deal("questions", len(WITS_QUESTIONS), ROUNDS, kind="wits")
        ]
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._ask()

    def _ask(self) -> None:
        self.answers: dict[str, int] = {}
        self.bets: dict[str, list[int]] = {}  # player -> slots their chips are on
        self.wagers: dict[str, int] = {}  # all-in round: player -> points on their one slot
        self.board: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None
        self.phase = "answer"
        self.set_deadline(self.timings["answer"])
        self.bump()

    def _open_bets(self) -> None:
        values = sorted(set(self.answers.values()))
        odds = board_odds(len(values))
        self.board = [{"slot": 0, "value": None, "by": [], "odds": odds[0]}] + [
            {
                "slot": i + 1,
                "value": v,
                "by": sorted(p for p, a in self.answers.items() if a == v),
                "odds": odds[i + 1],
            }
            for i, v in enumerate(values)
        ]
        self.phase = "bet"
        self.set_deadline(self.timings["bet"])
        self.bump()

    def _reveal(self) -> None:
        truth = self.questions[self.round]["a"]
        under = [s for s in self.board[1:] if s["value"] <= truth]
        win = under[-1] if under else self.board[0]
        gains: dict[str, int] = {p.id: 0 for p in self.players}
        for pid, slots in self.bets.items():
            if self.all_in:
                stake = self.wagers[pid]
                gains[pid] += stake * win["odds"] if slots[0] == win["slot"] else -stake
            else:
                gains[pid] += sum(CHIP_VALUE * win["odds"] for s in slots if s == win["slot"])
        for pid in win["by"]:
            gains[pid] += AUTHOR_BONUS
        for pid, g in gains.items():
            self.add_points(pid, g)
        self.result = {
            "answer": truth,
            "slot": win["slot"],
            "gains": gains,
            "bets": {p: list(s) for p, s in self.bets.items()},
            "wagers": dict(self.wagers),
            "answers": dict(self.answers),
        }
        self.history.append({"q": self.questions[self.round]["q"], **self.result})
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= ROUNDS:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._ask()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "answer":
            if self.phase != "answer":
                raise GameError("wrong_phase", "Answers are closed")
            if pid in self.answers:
                raise GameError("already_locked", "Your answer is in")
            self.answers[pid] = as_int(action.get("value"), lo=0, hi=MAX_ANSWER, field="Answer")
            self.bump()
            if len(self.answers) == len(self.players):
                self._open_bets()
            return
        if kind == "bet":
            if self.phase != "bet":
                raise GameError("wrong_phase", "Betting is closed")
            if pid in self.bets:
                raise GameError("already_locked", "Your chips are down")
            slots = action.get("slots")
            need = 1 if self.all_in else CHIPS
            if not isinstance(slots, list) or len(slots) != need:
                raise GameError(
                    "bad_input", "Pick one slot" if self.all_in else f"Place exactly {CHIPS} chips"
                )
            picked = [as_int(s, lo=0, hi=len(self.board) - 1, field="Slot") for s in slots]
            if self.all_in:
                self.wagers[pid] = as_int(action.get("wager"), lo=0, hi=self.max_wager(pid), field="Wager")
            self.bets[pid] = picked
            self.bump()
            if len(self.bets) == len(self.players):
                self._reveal()
            return
        raise GameError("bad_action", "Unknown action")

    @property
    def all_in(self) -> bool:
        return self.round == ROUNDS - 1

    def max_wager(self, pid: str) -> int:
        return max(self.round_scores.get(pid, 0), ALL_IN_FLOOR)

    def peek(self, pid: str) -> str | None:
        """Power card: whether the true answer is above or below a number on the board."""
        if self.phase != "bet" or len(self.board) < 2:
            return None
        slot = self.rng.choice(self.board[1:])
        side = "at or above" if self.questions[self.round]["a"] >= slot["value"] else "below"
        return f"The real answer is {side} {slot['value']:,}."

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "answer":
            self._open_bets()
        elif self.phase == "bet":
            self._reveal()
        elif self.phase == "reveal":
            self._next()

    def view_for(self, pid: str) -> dict[str, Any]:
        q = self.questions[self.round]
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "question": {"q": q["q"], "unit": q["unit"]},  # never the answer before the reveal
            "answered": sorted(self.answers) if self.phase == "answer" else [],
            "board": [dict(s) for s in self.board],
            "bet_in": sorted(self.bets) if self.phase == "bet" else [],
            "chips": CHIPS,
            "chip_value": CHIP_VALUE,
            "all_in": self.all_in,
            "you": {
                "answer": self.answers.get(pid),
                "bets": list(self.bets.get(pid, [])) if self.phase == "bet" else None,
                "wager": self.wagers.get(pid) if self.phase == "bet" else None,
                "max_wager": self.max_wager(pid) if pid in self.round_scores else 0,
            },
        }
        if self.phase in ("reveal", "final") and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        best = max(
            ((p, g) for h in self.history for p, g in h["gains"].items()), key=lambda x: x[1], default=None
        )
        if best and best[1] > 0:
            out.append(
                {
                    "icon": "🎰",
                    "title": "Big bettor",
                    "text": f"{self.name_of(best[0])} won {best[1]} on one question",
                }
            )
        exact = [(p, h) for h in self.history for p, a in h["answers"].items() if a == h["answer"]]
        if exact:
            p, h = exact[0]
            out.append(
                {"icon": "🤓", "title": "Knew it exactly", "text": f"{self.name_of(p)} said {h['answer']}"}
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
