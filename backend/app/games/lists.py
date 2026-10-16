"""Letter Lists (Scattergories rules, our own name): one letter, six categories, beat the clock.

Each round deals a letter and six categories. Everyone writes an answer for each category that starts
with that letter ("Animals" + B: "Bear") before the clock runs out; answers save as you type. Then the
room reviews every answer together and can vote down any it won't accept (more than half of the other
players saying no rejects it). A valid answer nobody else gave scores 100; an answer someone else also
gave scores nothing (the original's rule), and so does a blank, a wrong letter or a rejected answer.
Letters come from the original's set: no Q, U, V, X, Y or Z.

Secrecy: answers stay hidden until the review (others only see who is done). A host can skip the
review and the scores, not the writing.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import LIST_CATEGORIES

LETTERS = "ABCDEFGHIJKLMNOPRSTW"
PER_ROUND = 6
MAX_ANSWER = 30
POINTS = 100


def key(text: str) -> str:
    """What counts as the same answer: letters and digits only, any case, without a leading "the"/"a"."""
    s = re.sub(r"[^0-9a-z ]", "", text.casefold()).strip()
    s = re.sub(r"^(the|a|an) ", "", s)
    return s.replace(" ", "")


def starts_with(text: str, letter: str) -> bool:
    s = re.sub(r"^(the|a|an) ", "", text.strip().casefold())
    first = next((c for c in s if c.isalnum()), "")
    return first == letter.casefold()


class LetterLists(Game):
    game_id: ClassVar[str] = "lists"
    title: ClassVar[str] = "Letter Lists"
    blurb: ClassVar[str] = (
        "One letter, six categories, one clock. Fill them all, then the room judges. Only answers nobody "
        "else thought of score."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"lists": ["3", "2", "5"], "writing": ["90", "60", "120"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Each round: one letter and six categories. Write an answer for each that starts with the letter.",
        "Answers save as you type. Tap Done when you're happy (the clock ends it anyway).",
        "Then the room checks every answer. Vote no on any you won't accept.",
        "A good answer nobody else gave: 100. The same answer as someone else: nothing!",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["review", "scores"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"review": 75.0, "scores": 12.0}

    def start(self) -> None:
        self.rounds = int(self.options.get("lists", "3"))
        self.write_seconds = float(self.options.get("writing", "90"))
        letters = list(LETTERS)
        self.rng.shuffle(letters)
        self.letters = letters[: self.rounds]
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._deal()

    def _deal(self) -> None:
        picks = self.deal("categories", len(LIST_CATEGORIES), PER_ROUND, kind="lists")
        self.categories = [LIST_CATEGORIES[i] for i in picks]
        self.letter = self.letters[self.round]
        self.answers: dict[str, list[str]] = {p: [""] * PER_ROUND for p in self.player_ids}
        self.done: set[str] = set()
        self.nopes: dict[tuple[str, int], set[str]] = {}  # (author, category) -> who voted no
        self.result: dict[str, Any] | None = None
        self.phase = "write"
        self.set_deadline(self.write_seconds)
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "answers":
            self._answers(pid, action.get("answers"), action.get("done"))
        elif kind == "nope":
            self._nope(pid, action.get("who"), action.get("i"))
        else:
            raise GameError("bad_action", "Unknown action")

    def _answers(self, pid: str, raw: Any, done: Any) -> None:
        if self.phase != "write":
            raise GameError("wrong_phase", "Pens down: writing is over")
        if not isinstance(raw, list) or len(raw) != PER_ROUND:
            raise GameError("bad_input", f"Send {PER_ROUND} answers")
        clean: list[str] = []
        for text in raw:
            if not isinstance(text, str) or not text.isprintable():
                raise GameError("bad_input", "Answers are plain text")
            text = " ".join(text.split())
            if len(text) > MAX_ANSWER:
                raise GameError("bad_input", f"Keep each answer to {MAX_ANSWER} characters")
            clean.append(text)
        if not isinstance(done, bool):
            raise GameError("bad_input", "Done or not?")
        self.answers[pid] = clean
        if done:
            self.done.add(pid)
        else:
            self.done.discard(pid)
        self.bump()
        if self.done >= set(self.player_ids):
            self._review()

    def _nope(self, pid: str, who: Any, i: Any) -> None:
        if self.phase != "review":
            raise GameError("wrong_phase", "Voting is closed")
        if not isinstance(who, str) or who not in self.answers:
            raise GameError("bad_input", "Whose answer?")
        if who == pid:
            raise GameError("own_answer", "You can't vote on your own answer")
        n = as_int(i, lo=0, hi=PER_ROUND - 1, field="Category")
        if not self.answers[who][n]:
            raise GameError("bad_input", "There's no answer there")
        votes = self.nopes.setdefault((who, n), set())
        if pid in votes:
            votes.discard(pid)
        else:
            votes.add(pid)
        self.bump()

    # -- rounds ---------------------------------------------------------------------------------------
    def _review(self) -> None:
        self.phase = "review"
        self.set_deadline(self.timings["review"])
        self.bump()

    def _rejected(self, who: str, i: int) -> bool:
        others = len(self.player_ids) - 1
        return len(self.nopes.get((who, i), set())) * 2 > others

    def _score(self) -> None:
        status: dict[str, list[str]] = {p: [] for p in self.player_ids}
        gains = {p: 0 for p in self.player_ids}
        for i in range(PER_ROUND):
            good: dict[str, str] = {}
            for p in self.player_ids:
                text = self.answers[p][i]
                if not text or not starts_with(text, self.letter):
                    status[p].append("bad")
                elif self._rejected(p, i):
                    status[p].append("nope")
                else:
                    good[p] = key(text)
                    status[p].append("")
            counts: dict[str, int] = {}
            for k in good.values():
                counts[k] = counts.get(k, 0) + 1
            for p, k in good.items():
                if counts[k] > 1:
                    status[p][i] = "same"
                else:
                    status[p][i] = "ok"
                    gains[p] += POINTS
        for p, g in gains.items():
            self.add_points(p, g)
        self.result = {"status": status, "gains": gains}
        self.history.append(
            {
                "letter": self.letter,
                "categories": list(self.categories),
                "answers": dict(self.answers),
                **self.result,
            }
        )
        self.phase = "scores"
        self.set_deadline(self.timings["scores"])
        self.bump()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "write":
            self._review()
        elif self.phase == "review":
            self._score()
        elif self.phase == "scores":
            if self.round + 1 >= self.rounds:
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.bump()
            else:
                self.round += 1
                self._deal()

    def skip(self) -> bool:
        """The review and the scores; never the writing (that would cut off whoever is still writing)."""
        if self.phase == "write":
            return False
        self.advance()
        return True

    def peek(self, pid: str) -> str | None:
        """Power card: how far the fastest writer has got (never what they wrote)."""
        if self.phase != "write":
            return None
        most = max(sum(1 for a in ans if a) for p, ans in self.answers.items() if p != pid)
        return f"The busiest pen in the room has {most} of {PER_ROUND} answers so far."

    def chat_muted(self, pid: str) -> bool:
        return self.phase == "write"  # no sharing answers while the clock runs

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        seated = pid in self.round_scores
        open_book = self.phase in ("review", "scores", "final")
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "letter": self.letter,
            "categories": list(self.categories),
            "done": sorted(self.done) if self.phase == "write" else [],
            "answers": {p: list(a) for p, a in self.answers.items()} if open_book else None,
            "nopes": {f"{w}:{i}": len(v) for (w, i), v in self.nopes.items() if v} if open_book else {},
            "scores": self.scores(),
            "you": {
                "answers": list(self.answers[pid]),
                "done": pid in self.done,
                "noped": sorted(f"{w}:{i}" for (w, i), v in self.nopes.items() if pid in v),
            }
            if seated
            else None,
        }
        if self.phase in ("scores", "final") and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = [{"letter": h["letter"], "gains": h["gains"]} for h in self.history]
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        best = max(((h["gains"][p], p, h["letter"]) for h in self.history for p in h["gains"]), default=None)
        if best and best[0] > 0:
            text = f"{self.name_of(best[1])} scored {best[0]} on {best[2]}"
            out.append({"icon": "📝", "title": "Full house", "text": text})
        twins = self._great_minds()
        if twins:
            who, answer = twins
            names = " & ".join(self.name_of(q) for q in who[:3])
            text = f"{names} {'both' if len(who) == 2 else 'all'} wrote “{answer}”"
            out.append({"icon": "🧠", "title": "Great minds", "text": text})
        return out

    def _great_minds(self) -> tuple[list[str], str] | None:
        """The first answer that two or more players gave (and so all lost)."""
        for h in self.history:
            for i in range(PER_ROUND):
                groups: dict[str, list[str]] = {}
                for p, marks in h["status"].items():
                    if marks[i] == "same":
                        groups.setdefault(key(h["answers"][p][i]), []).append(p)
                for who in groups.values():
                    return who, h["answers"][who[0]][i]
        return None

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
