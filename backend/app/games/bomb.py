"""Hot Potato Bomb: a ticking bomb goes round the circle; answer the prompt to pass it on.

Each round has one "name one" prompt. Whoever holds the bomb types an answer nobody has given yet this
round, and the bomb jumps to the next player still in. The fuse is a random length that only the server
knows: no screen is ever told how long is left. Whoever holds it when it goes off loses a life; out of
lives, out of the game. The last player standing wins.

Answers aren't judged (the room does that out loud), they only have to be new for this round.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, ClassVar

from .base import Game, GameError
from .content import BOMB_PROMPTS

FUSE = (14.0, 38.0)  # seconds, picked at random each round
ANSWER, SURVIVE, WIN = 50, 100, 500
MAX_ANSWER = 30
SHOWN = 10  # answers kept on screen


def fold(text: str) -> str:
    """Letters and digits only, lower-cased, accents dropped: 'An Apple!' and 'an apple' are one answer."""
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(ch for ch in text if ch.isalnum())


class HotPotatoBomb(Game):
    game_id: ClassVar[str] = "bomb"
    title: ClassVar[str] = "Hot Potato Bomb"
    blurb: ClassVar[str] = (
        "A ticking bomb goes round the circle. Type an answer nobody has used to pass it on. "
        "Hold it when it blows and you lose a life."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    OPTIONS: ClassVar[dict[str, list[str]]] = {"lives": ["3", "2", "1", "5"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "The bomb starts with one player. Everyone sees the same prompt, like “a fruit that isn’t red”.",
        "Holding it? Type any answer nobody has given this round and it jumps to the next player.",
        "Nobody knows how long the fuse is. Holding it when it blows costs a life.",
        "Out of lives, out of the game. Last one standing wins.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["boom"])
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"boom": 7.0, "fuse_min": FUSE[0], "fuse_max": FUSE[1]}

    def start(self) -> None:
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        lives = int(self.options.get("lives", "3"))
        self.lives: dict[str, int] = dict.fromkeys(self.order, lives)
        self.out: list[str] = []  # in the order they went out
        self.holder = self.rng.choice(self.order)
        self.passes: dict[str, int] = dict.fromkeys(self.order, 0)
        self.blasts: list[dict[str, Any]] = []
        self.boom: dict[str, Any] | None = None
        self.round = 0
        self._light()

    def _alive(self) -> list[str]:
        return [p for p in self.order if self.lives[p] > 0]

    def _next(self, pid: str) -> str:
        alive = self._alive()
        i = self.order.index(pid)
        return next(p for p in self.order[i + 1 :] + self.order[: i + 1] if p in alive)

    def _light(self) -> None:
        """A new round: a new prompt and a fresh fuse of a length nobody is told."""
        self.round += 1
        (pick,) = self.deal("prompts", len(BOMB_PROMPTS), 1)
        self.prompt = BOMB_PROMPTS[pick]
        self.answers: list[dict[str, str]] = []
        self.used: set[str] = set()
        self.boom = None
        self.phase = "pass"
        self.deadline = None  # the fuse is not a public countdown
        self.fuse_at = self.clock() + self.rng.uniform(self.timings["fuse_min"], self.timings["fuse_max"])
        self.bump()

    def _explode(self) -> None:
        victim = self.holder
        self.lives[victim] -= 1
        gone = self.lives[victim] == 0
        if gone:
            self.out.append(victim)
        for pid in self._alive():
            if pid != victim:
                self.add_points(pid, SURVIVE)
        self.boom = {"who": victim, "out": gone, "prompt": self.prompt, "answers": len(self.answers)}
        self.blasts.append(dict(self.boom))
        self.phase = "boom"
        self.set_deadline(self.timings["boom"])
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "answer":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "pass":
            raise GameError("wrong_phase", "The bomb isn't live")
        if pid != self.holder:
            raise GameError("not_yours", "You're not holding the bomb")
        raw = action.get("text")
        if not isinstance(raw, str):
            raise GameError("bad_input", "Type an answer")
        text = re.sub(r"\s+", " ", raw).strip()
        if any(unicodedata.category(ch)[0] == "C" for ch in text):
            raise GameError("bad_input", "That answer has characters we can't use")
        key = fold(text)
        if len(key) < 2 or len(text) > MAX_ANSWER:
            raise GameError("bad_input", f"2-{MAX_ANSWER} characters, please")
        if key in self.used:
            raise GameError("used", "Someone already said that!")
        self.used.add(key)
        self.answers.append({"by": pid, "text": text})
        self.passes[pid] += 1
        self.add_points(pid, ANSWER)
        self.holder = self._next(pid)
        self.bump()

    def tick(self) -> None:
        if self.finished:
            return
        if self.phase == "pass" and self.clock() >= self.fuse_at:
            self._explode()
        elif self.phase == "boom" and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "pass":
            self._explode()
            return
        alive = self._alive()
        if len(alive) <= 1:
            if alive:
                self.add_points(alive[0], WIN)
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        victim = self.boom["who"] if self.boom else self.holder
        self.holder = victim if victim in alive else self._next(victim)  # whoever it blew up on starts
        self._light()

    def view_for(self, pid: str) -> dict[str, Any]:
        """Everything here is public. The one secret, the fuse, is never part of any view."""
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "order": list(self.order),
            "lives": dict(self.lives),
            "out": list(self.out),
            "holder": self.holder if self.phase == "pass" else None,
            "prompt": self.prompt,
            "answers": self.answers[-SHOWN:],
            "count": len(self.answers),
            "boom": self.boom if self.phase == "boom" else None,
            "passes": dict(self.passes),
        }
        if self.phase == "final":
            alive = self._alive()
            view["winner"] = alive[0] if alive else None
            view["scores"] = self.scores()
            view["blasts"] = self.blasts
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        alive = self._alive()
        if alive:
            out.append(
                {"icon": "🏆", "title": "Bomb proof", "text": f"{self.name_of(alive[0])} outlasted everyone"}
            )
        quick = max(self.passes.items(), key=lambda kv: kv[1])
        if quick[1] >= 3:
            out.append(
                {
                    "icon": "⚡",
                    "title": "Quick hands",
                    "text": f"{self.name_of(quick[0])} passed it {quick[1]} times",
                }
            )
        hits: dict[str, int] = {}
        for b in self.blasts:
            hits[b["who"]] = hits.get(b["who"], 0) + 1
        if hits:
            who, n = max(hits.items(), key=lambda kv: kv[1])
            if n >= 2:
                out.append(
                    {
                        "icon": "💥",
                        "title": "Bomb magnet",
                        "text": f"It blew up on {self.name_of(who)} {n} times",
                    }
                )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": self.round, "answers": sum(self.passes.values())}
