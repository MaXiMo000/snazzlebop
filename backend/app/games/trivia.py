"""Trivia Tonight: the quiz show. 1,300+ questions in 15 categories, five ways to play.

Everyone answers the same question on their phone (four choices, or true or false) before the clock
runs out. Styles (host option):
- classic: right = 500 + up to 500 for speed, plus a streak bonus from the third right answer in a row.
- fastest: the first right answer takes 1,000, any other right answer 250, a wrong one costs 250.
- survival: three lives; a wrong answer or no answer costs one. Last one standing wins (+500).
- wager: the category and level are shown first and everyone bets on themselves (0 up to their score,
  or 300 if that's more). Right: +100 + the bet. Wrong or silent: minus the bet.
- draft: classic scoring, but each round one player picks the category from three.
Topic: everything mixed (default) or one category. Level: "ramp" starts easy and gets harder.

Secrecy: the right answer and everyone's choices stay hidden until the reveal (players only see who
has locked in); wagers stay hidden until the question; the TV and the audience never hold a choice.
A host can skip the reading phases but not a running question (the clock ends it).
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .trivia_bank import CATEGORIES, TRIVIA

STYLES = ("classic", "fastest", "survival", "wager", "draft")
LIVES = 3
SURVIVAL_CAP = 50  # survival questions at most, so a room of quiz wizards still goes home
WAGER_FLOOR = 300  # the most anyone can bet when their score is lower than this
OFFERS = 3  # categories on the table in a draft pick
# A themed show pack leans on the matching category (most of the questions, not all).
THEME_CATEGORY = {"movies": "screen", "sports": "sport", "food": "food"}
THEME_SHARE = 0.6


def _by_cat_level() -> dict[tuple[str, int], list[int]]:
    """(category, level) -> indices into TRIVIA. Rebuilt when generated questions arrive."""
    out: dict[tuple[str, int], list[int]] = {}
    for i, q in enumerate(TRIVIA):
        out.setdefault((q["cat"], q["level"]), []).append(i)
    return out


_INDEX: tuple[int, dict[tuple[str, int], list[int]]] = (0, {})


def index() -> dict[tuple[str, int], list[int]]:
    global _INDEX
    if _INDEX[0] != len(TRIVIA):
        _INDEX = (len(TRIVIA), _by_cat_level())
    return _INDEX[1]


class TriviaTonight(Game):
    game_id: ClassVar[str] = "trivia"
    title: ClassVar[str] = "Trivia Tonight"
    blurb: ClassVar[str] = (
        "The quiz show: 1,300+ questions in 15 categories. Classic, fastest finger, survival, high stakes "
        "or category draft. Speed counts!"
    )
    min_players: ClassVar[int] = 1
    max_players: ClassVar[int] = 8
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {
        "style": list(STYLES),
        "questions": ["10", "15", "20", "5"],
        "topic": ["mix", *CATEGORIES],
        "level": ["ramp", "easy", "medium", "hard"],
        "timer": ["20", "15", "30"],
    }
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone gets the same question. Tap your answer before the clock runs out: one try, no changes.",
        "Classic: a right answer scores 500, plus up to 500 more for speed. Three right in a row starts a "
        "streak bonus.",
        "Fastest finger: the first right answer takes 1,000. Other right answers 250, a wrong one costs 250.",
        "Survival: three lives. A wrong answer (or none) costs a life. Last one standing wins.",
        "High stakes: see the category, then bet on yourself. Right wins your bet, wrong loses it.",
        "Category draft: take turns picking the next question's category.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["reveal"])
    CHAT_MUTED_NOTE: ClassVar[str] = "No chat while a question is up: no helping!"

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"pick": 12.0, "wager": 12.0, "reveal": 9.0}

    # -- setup ------------------------------------------------------------------------------------
    def start(self) -> None:
        self.style = self.options.get("style", STYLES[0])
        self.topic = self.options.get("topic", "mix")
        self.level_opt = self.options.get("level", "ramp")
        self.limit = float(self.options.get("timer", "20"))
        self.total = SURVIVAL_CAP if self.style == "survival" else int(self.options.get("questions", "10"))
        if self.topic != "mix" and self.style == "draft":
            self.style = "classic"  # nothing to draft with one category
        self.lives: dict[str, int] = {p.id: LIVES for p in self.players} if self.style == "survival" else {}
        self.out_order: list[str] = []  # survival: eliminated players, first out first
        self.streak: dict[str, int] = {p.id: 0 for p in self.players}
        self.best_streak: dict[str, int] = {p.id: 0 for p in self.players}
        self.correct: dict[str, int] = {p.id: 0 for p in self.players}
        self.used: set[int] = set()
        self.last_cat = ""
        self.history: list[dict[str, Any]] = []
        self.fastest_ms: tuple[str, int] | None = None
        self.big_bet: tuple[str, int] | None = None
        self.round = 0
        self._round_start()

    def _level_for(self, i: int) -> int:
        if self.level_opt != "ramp":
            return {"easy": 1, "medium": 2, "hard": 3}[self.level_opt]
        if self.style == "survival":
            return 1 if i < 5 else 2 if i < 15 else 3
        frac = i / max(1, self.total - 1)
        return 1 if frac < 0.3 else 2 if frac < 0.75 else 3

    def _category(self) -> str:
        if self.topic != "mix":
            return self.topic
        themed = THEME_CATEGORY.get(self.theme)
        if themed and self.rng.random() < THEME_SHARE:
            return themed
        cats = [c for c in CATEGORIES if c != self.last_cat]
        return self.rng.choice(cats)

    def _deal(self, cat: str, level: int) -> int:
        """A question this game hasn't asked yet: the wanted level first, then the nearest ones."""
        idx = index()
        for lv in sorted((1, 2, 3), key=lambda x: (abs(x - level), -x)):
            pool = idx.get((cat, lv), [])
            if not pool:
                continue
            for _ in range(len(pool)):  # at most one pass of this room's deck, then the next level
                pick = pool[self.deal(f"{cat}:{lv}", len(pool), 1)[0]]
                if pick not in self.used:
                    return pick
        # Every question of this category has been asked this game: allow repeats rather than stall.
        pool = [i for lv in (1, 2, 3) for i in idx.get((cat, lv), [])]
        return self.rng.choice(pool)

    def _round_start(self) -> None:
        self.answers: dict[str, tuple[int, int]] = {}  # pid -> (choice, ms after the question appeared)
        self.wagers: dict[str, int] = {}
        self.result: dict[str, Any] | None = None
        self.qi: int | None = None
        self.choices: list[str] = []
        self.cat = ""
        self.offers: list[str] = []
        self.picker: str | None = None
        if self.style == "draft":
            self.picker = self.player_ids[self.round % len(self.players)]
            cats = list(CATEGORIES)
            self.rng.shuffle(cats)
            self.offers = [c for c in cats if c != self.last_cat][:OFFERS]
            self.phase = "pick"
            self.set_deadline(self.timings["pick"])
            self.bump()
            return
        self._choose(self._category())

    def _choose(self, cat: str) -> None:
        self.cat = cat
        self.last_cat = cat
        self.qi = self._deal(cat, self._level_for(self.round))
        self.used.add(self.qi)
        q = TRIVIA[self.qi]
        if len(q["wrong"]) == 1:
            self.choices = ["True", "False"]
        else:
            self.choices = [q["a"], *q["wrong"]]
            self.rng.shuffle(self.choices)
        if self.style == "wager":
            self.phase = "wager"
            self.set_deadline(self.timings["wager"])
            self.bump()
            return
        self._ask()

    def _ask(self) -> None:
        self.phase = "question"
        self.set_deadline(self.limit)
        self.asked_at = self.clock()
        self.bump()

    # -- who is still playing ----------------------------------------------------------------------
    def alive(self, pid: str) -> bool:
        return self.style != "survival" or self.lives.get(pid, 0) > 0

    @property
    def in_play(self) -> list[str]:
        return [p for p in self.player_ids if self.alive(p)]

    def max_wager(self, pid: str) -> int:
        return max(self.round_scores.get(pid, 0), WAGER_FLOOR)

    # -- actions ----------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "pick":
            if self.phase != "pick":
                raise GameError("wrong_phase", "No category to pick right now")
            if pid != self.picker:
                raise GameError("not_your_pick", "It's someone else's pick")
            cat = action.get("cat")
            if not isinstance(cat, str) or cat not in self.offers:
                raise GameError("bad_input", "Pick one of the three categories")
            self._choose(cat)
            return
        if kind == "wager":
            if self.phase != "wager":
                raise GameError("wrong_phase", "Bets are closed")
            if pid in self.wagers:
                raise GameError("already_locked", "Your bet is in")
            self.wagers[pid] = as_int(action.get("amount"), lo=0, hi=self.max_wager(pid), field="Bet")
            self.bump()
            if len(self.wagers) == len(self.players):
                self._ask()
            return
        if kind == "answer":
            if self.phase != "question":
                raise GameError("wrong_phase", "Too late: answers are closed")
            if not self.alive(pid):
                raise GameError("out", "You're out of lives: cheer the others on")
            if pid in self.answers:
                raise GameError("already_locked", "Your answer is locked in")
            choice = as_int(action.get("choice"), lo=0, hi=len(self.choices) - 1, field="Choice")
            ms = int(max(0.0, self.clock() - self.asked_at) * 1000)
            self.answers[pid] = (choice, ms)
            self.bump()
            if all(p in self.answers for p in self.in_play):
                self._reveal()
            return
        raise GameError("bad_action", "Unknown action")

    # -- scoring ----------------------------------------------------------------------------------
    def _reveal(self) -> None:
        q = TRIVIA[self.qi] if self.qi is not None else None
        right = self.choices.index(q["a"]) if q else 0
        gains: dict[str, int] = {p: 0 for p in self.player_ids}
        hits = sorted(
            ((ms, p) for p, (c, ms) in self.answers.items() if c == right),
        )
        first = hits[0][1] if hits else None
        newly_out: list[str] = []
        for pid in self.in_play:
            ans = self.answers.get(pid)
            ok = ans is not None and ans[0] == right
            if ok:
                self.correct[pid] += 1
                self.streak[pid] += 1
                self.best_streak[pid] = max(self.best_streak[pid], self.streak[pid])
                ms = ans[1]
                if self.fastest_ms is None or ms < self.fastest_ms[1]:
                    self.fastest_ms = (pid, ms)
            else:
                self.streak[pid] = 0
            if self.style in ("classic", "draft"):
                if ok:
                    speed = max(0.0, 1 - ans[1] / 1000 / self.limit)
                    gains[pid] = (
                        500 + int(round(500 * speed / 10)) * 10 + 100 * min(3, max(0, self.streak[pid] - 2))
                    )
            elif self.style == "fastest":
                gains[pid] = (1000 if pid == first else 250) if ok else (-250 if ans is not None else 0)
            elif self.style == "survival":
                if ok:
                    gains[pid] = 100
                else:
                    self.lives[pid] -= 1
                    if self.lives[pid] == 0:
                        newly_out.append(pid)
            elif self.style == "wager":
                bet = self.wagers.get(pid, 0)
                gains[pid] = 100 + bet if ok else -bet
                if ok and bet and (self.big_bet is None or bet > self.big_bet[1]):
                    self.big_bet = (pid, bet)
        self.out_order.extend(newly_out)
        for pid, g in gains.items():
            self.add_points(pid, g)
        self.result = {
            "right": right,
            "answer": q["a"] if q else "",
            "picks": {p: c for p, (c, _) in self.answers.items()},
            "times": {p: ms for p, (_, ms) in self.answers.items()},
            "gains": gains,
            "first": first,
            "out": newly_out,
            "wagers": dict(self.wagers),
        }
        if q:
            self.history.append(
                {"q": q["q"], "a": q["a"], "cat": q["cat"], "right": sorted(p for _, p in hits)}
            )
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _over(self) -> bool:
        if self.round + 1 >= self.total:
            return True
        if self.style != "survival":
            return False
        left = len(self.in_play)
        return left == 0 or (left == 1 and len(self.players) > 1)

    def _next(self) -> None:
        if self._over():
            if self.style == "survival":
                for pid in self.in_play:
                    self.add_points(pid, 500)  # the last one standing (or everyone who made it to the end)
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.round += 1
        self._round_start()

    # -- timers -----------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self._expire()

    def _expire(self) -> None:
        if self.phase == "pick":
            self._choose(self.rng.choice(self.offers))
        elif self.phase == "wager":
            self._ask()  # no bet = a bet of 0
        elif self.phase == "question":
            self._reveal()
        elif self.phase == "reveal":
            self._next()

    def advance(self) -> None:
        """Host skip: the picks, bets and the reveal, never a question that's still running."""
        if self.finished or self.phase == "question":
            return
        self._expire()

    def chat_muted(self, pid: str) -> bool:
        return self.phase == "question"

    def peek(self, pid: str) -> str | None:
        """Power card: 50:50. Names two wrong choices (one for a true-or-false question)."""
        if self.phase != "question" or self.qi is None or len(self.choices) < 4:
            return None
        wrong = [c for c in self.choices if c != TRIVIA[self.qi]["a"]]
        a, b = self.rng.sample(wrong, 2)
        return f"50:50. It isn't “{a}” and it isn't “{b}”."

    # -- what each screen sees -------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        seated = pid in self.round_scores
        q = TRIVIA[self.qi] if self.qi is not None else None
        label, icon = CATEGORIES.get(self.cat, ("", ""))
        showing = self.phase in ("question", "reveal") or (self.phase == "final" and q is not None)
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "style": self.style,
            "round": self.round + 1,
            "rounds": None if self.style == "survival" else self.total,
            "remaining": self.remaining(),
            "limit": self.limit,
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "category": {"id": self.cat, "label": label, "icon": icon} if self.cat else None,
            "level": q["level"] if q and self.phase != "pick" else None,
            "question": {"q": q["q"], "choices": list(self.choices), "tf": len(q["wrong"]) == 1}
            if q and showing
            else None,
            "answered": sorted(self.answers) if self.phase == "question" else [],
            "wagered": sorted(self.wagers) if self.phase == "wager" else [],
            "pick": {
                "picker": self.picker,
                "offers": [
                    {"id": c, "label": CATEGORIES[c][0], "icon": CATEGORIES[c][1]} for c in self.offers
                ],
            }
            if self.phase == "pick"
            else None,
            "lives": dict(self.lives),
            "streaks": {p: s for p, s in self.streak.items() if s >= 2},
            "scores": self.scores(),
            "you": {
                "answer": self.answers[pid][0] if pid in self.answers else None,
                "wager": self.wagers.get(pid),
                "max_wager": self.max_wager(pid),
                "streak": self.streak[pid],
                "lives": self.lives.get(pid),
                "out": not self.alive(pid),
            }
            if seated
            else None,
        }
        if self.phase in ("reveal", "final") and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = self.history
            view["correct"] = dict(self.correct)
            view["best_streak"] = dict(self.best_streak)
        return view

    # -- show night --------------------------------------------------------------------------------
    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        top = max(self.correct.items(), key=lambda x: x[1], default=None)
        if top and top[1] > 0:
            out.append(
                {"icon": "🧠", "title": "Brainiac", "text": f"{self.name_of(top[0])} got {top[1]} right"}
            )
        if self.fastest_ms:
            pid, ms = self.fastest_ms
            out.append(
                {
                    "icon": "⚡",
                    "title": "Fastest finger",
                    "text": f"{self.name_of(pid)} answered right in {ms / 1000:.1f} s",
                }
            )
        streak = max(self.best_streak.items(), key=lambda x: x[1], default=None)
        if streak and streak[1] >= 3:
            out.append(
                {
                    "icon": "🔥",
                    "title": "On fire",
                    "text": f"{self.name_of(streak[0])} got {streak[1]} in a row",
                }
            )
        if self.big_bet:
            pid, bet = self.big_bet
            out.append(
                {"icon": "🎲", "title": "High roller", "text": f"{self.name_of(pid)} bet {bet} and won"}
            )
        if self.style == "survival" and len(self.players) > 1 and len(self.in_play) == 1:
            out.append(
                {
                    "icon": "🛡️",
                    "title": "Last one standing",
                    "text": f"{self.name_of(self.in_play[0])} survived",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "questions": len(self.history), "style": self.style}
