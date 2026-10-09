"""Draw & Guess: one player draws a secret word, everyone else races to guess it (Scribble rules).

Each round every player draws once. The drawer picks one of three words (or gets one at random when the
clock runs out), then draws it while the others type guesses. Wrong guesses show up for everyone, like a
chat; a guess one letter off is "close", and only the guesser is told. A right guess is never shown.

Hints: the word's blanks are shown from the start, and letters are revealed as time runs down (one at
half time, another at three quarters for longer words), never the whole word.

Scoring: a right guess pays 100 + up to 300 more for speed (the share of the clock left). The drawer
gets 75 for every player who gets it. The turn ends when everyone has guessed or the clock runs out.

Secrecy: the word goes only to the drawer, and to each guesser once they've got it. The others (TV and
audience too) see only the blanks and hints until the reveal. The three choices go only to the drawer.

The drawing itself travels separately (see ink.py): the hub relays the drawer's strokes to every screen.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import DRAW_WORDS
from .ink import InkLog

ROUNDS = {"2": 2, "1": 1, "3": 3}
CHOICES = 3
GUESS_BASE, GUESS_SPEED, DRAWER_EACH = 100, 300, 75
MAX_GUESS = 32
KEEP_FEED = 40


def squash(text: str) -> str:
    """What counts when comparing a guess: letters only, any case ("Hot-dog" == "hotdog")."""
    return "".join(c for c in text.lower() if c.isalpha())


def one_off(a: str, b: str) -> bool:
    """True when a and b differ by exactly one letter added, dropped or changed."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


class DrawGuess(Game):
    game_id: ClassVar[str] = "drawguess"
    title: ClassVar[str] = "Draw & Guess"
    blurb: ClassVar[str] = (
        "Take turns drawing a secret word while everyone races to guess it. Faster guesses score more, "
        "and the artist scores for every right answer."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"turns": ["2", "1", "3"], "time": ["80", "60", "100"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Take turns to draw. The artist picks one of three secret words and draws it: no letters or numbers!",
        "Everyone else types guesses. Wrong guesses show for all; a near miss tells only you it's close.",
        "Letters of the word appear as the clock runs down.",
        "A right guess scores 100 plus up to 300 for speed. The artist gets 75 for each player who gets it.",
        "Everyone draws once a round.",
    )
    READING: ClassVar[frozenset[str]] = frozenset({"reveal"})

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"choose": 15.0, "reveal": 8.0}

    def start(self) -> None:
        self.total_rounds = ROUNDS.get(self.options.get("turns", "2"), 2)
        self.draw_seconds = float(self.options.get("time", "80"))
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        self.turn = 0  # across all rounds: round = turn // len(order)
        self.history: list[dict[str, Any]] = []
        self.canvas: InkLog | None = None
        self._choose()

    # -- turns ----------------------------------------------------------------------------------------
    @property
    def drawer(self) -> str:
        return self.order[self.turn % len(self.order)]

    def _choose(self) -> None:
        self.round = self.turn // len(self.order)
        self.choices = [DRAW_WORDS[i] for i in self.deal("words", len(DRAW_WORDS), CHOICES)]
        self.word = ""
        self.guessed: list[str] = []  # in the order they got it
        self.gained: dict[str, int] = {}
        self.feed: list[dict[str, Any]] = []
        self.hints: list[int] = []  # letter positions revealed so far
        self.canvas = None
        self.phase = "choose"
        self.set_deadline(self.timings["choose"])
        self.bump()

    def _draw(self, word: str) -> None:
        self.word = word
        letters = [i for i, c in enumerate(word) if c.isalpha()]
        self.rng.shuffle(letters)
        # Short words get one hint at most, longer ones two; never enough to give the word away.
        self.hint_order = letters[: min(2, max(0, (len(letters) - 1) // 2))]
        self.canvas = InkLog()
        self.phase = "draw"
        self.set_deadline(self.draw_seconds)
        self.bump()

    def _guessers(self) -> list[str]:
        return [p for p in self.player_ids if p != self.drawer]

    def _reveal(self) -> None:
        self.history.append(
            {
                "drawer": self.drawer,
                "word": self.word,
                "guessed": list(self.guessed),
                "points": dict(self.gained),
            }
        )
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "pick":
            if self.phase != "choose" or pid != self.drawer:
                raise GameError("not_your_turn", "It's not your turn to pick")
            self._draw(self.choices[as_int(action.get("i"), lo=0, hi=CHOICES - 1, field="choice")])
        elif kind == "guess":
            self._guess(pid, action.get("text"))
        else:
            raise GameError("bad_action", "Unknown action")

    def _guess(self, pid: str, raw: Any) -> None:
        if self.phase != "draw":
            raise GameError("wrong_phase", "Wait for the drawing")
        if pid == self.drawer:
            raise GameError("drawer", "You're drawing: no guessing your own word!")
        if pid in self.guessed:
            raise GameError("finished", "You've already got it")
        if not isinstance(raw, str) or not raw.isprintable():  # no control or invisible characters
            raise GameError("bad_input", "Type a guess")
        text = " ".join(raw.split())
        if not text or len(text) > MAX_GUESS:
            raise GameError("bad_input", f"Guesses are 1-{MAX_GUESS} characters")
        said, word = squash(text), squash(self.word)
        if said == word:
            self.guessed.append(pid)
            left = (self.remaining() or 0.0) / self.draw_seconds
            points = GUESS_BASE + round(GUESS_SPEED * left)
            self.gained[pid] = points
            self.add_points(pid, points)
            self.gained[self.drawer] = self.gained.get(self.drawer, 0) + DRAWER_EACH
            self.add_points(self.drawer, DRAWER_EACH)
            self.feed.append({"by": pid, "ok": True})
        else:
            close = len(word) >= 4 and one_off(said, word)
            self.feed.append({"by": pid, "text": text, "close": close})
        self.feed = self.feed[-KEEP_FEED:]
        self.bump()
        if len(self.guessed) >= len(self._guessers()):
            self._reveal()

    def ink(self, pid: str, msg: dict[str, Any]) -> InkLog:
        """A pen operation from the drawer (relayed by the hub). Returns the canvas it went on."""
        if self.phase != "draw" or self.canvas is None:
            raise GameError("wrong_phase", "Not drawing right now")
        if pid != self.drawer:
            raise GameError("not_your_turn", "Only the artist can draw")
        self.canvas.add(msg)
        return self.canvas

    def canvas_for(self, pid: str) -> InkLog | None:
        """Everyone (TV and audience too) watches the same drawing."""
        return self.canvas

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if self.finished:
            return
        if self.expired():
            self.advance()
        elif self.phase == "draw":
            left = (self.remaining() or 0.0) / self.draw_seconds
            due = (left <= 0.5) + (left <= 0.25)
            if len(self.hints) < min(due, len(self.hint_order)):
                self.hints.append(self.hint_order[len(self.hints)])
                self.bump()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "choose":
            self._draw(self.rng.choice(self.choices))
        elif self.phase == "draw":
            self._reveal()
        elif self.phase == "reveal":
            self.turn += 1
            if self.turn >= self.total_rounds * len(self.order):
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.canvas = None
                self.bump()
            else:
                self._choose()

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        out_loud = self.phase in ("reveal", "final")
        knows = out_loud or pid == self.drawer or pid in self.guessed
        word = self.word if self.phase != "choose" else ""
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.total_rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "order": list(self.order),
            "drawer": self.drawer if self.phase != "final" else None,
            "seconds": self.draw_seconds,
            "word": word if knows else None,
            # The blanks: "" for a hidden letter, the letter itself for a hint, spaces and dashes as-is.
            "pattern": [c if not c.isalpha() or i in self.hints or knows else "" for i, c in enumerate(word)],
            "choices": list(self.choices) if self.phase == "choose" and pid == self.drawer else None,
            "guessed": list(self.guessed),
            "gained": dict(self.gained),
            "feed": [{k: v for k, v in f.items() if k != "close" or f["by"] == pid} for f in self.feed],
            "ink": self.canvas.view() if self.canvas is not None else None,
            "you": {
                "drawer": pid == self.drawer and self.phase != "final",
                "guessed": pid in self.guessed,
                "playing": pid in self.round_scores,
            },
            "scores": self.scores(),
        }
        if self.phase == "final":
            view["history"] = self.history
        return view

    def peek(self, pid: str) -> str | None:
        if self.phase != "draw" or pid == self.drawer or pid in self.guessed:
            return None
        return f'The word starts with "{self.word[0].upper()}"'

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        art = [(len(h["guessed"]), h["drawer"], h["word"]) for h in self.history]
        if art:
            n, p, word = max(art, key=lambda a: a[0])
            if n:
                out.append(
                    {
                        "icon": "🎨",
                        "title": "Picasso",
                        "text": f"{n} {'player' if n == 1 else 'players'} got {self.name_of(p)}'s {word}",
                    }
                )
        firsts: dict[str, int] = {}
        for h in self.history:
            if h["guessed"]:
                firsts[h["guessed"][0]] = firsts.get(h["guessed"][0], 0) + 1
        if firsts:
            p = max(firsts, key=lambda q: firsts[q])
            out.append(
                {"icon": "⚡", "title": "Quick draw", "text": f"{self.name_of(p)} guessed first {firsts[p]}x"}
            )
        stumped = [h for h in self.history if not h["guessed"]]
        if stumped:
            h = stumped[0]
            out.append(
                {
                    "icon": "🤷",
                    "title": "Abstract art",
                    "text": f"Nobody guessed {self.name_of(h['drawer'])}'s {h['word']}",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        turns = len(self.history)
        return {
            "players": len(self.players),
            "turns": turns,
            "guessed_share": round(
                sum(len(h["guessed"]) for h in self.history) / max(turns * (len(self.players) - 1), 1), 2
            ),
        }
