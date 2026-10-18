"""Imposter: everyone gets the secret word except one. Give a clue, then find the faker.

Each round the crew all see the same secret word and its category; one player, the imposter, sees only
the category. Taking turns, everyone gives a one-word clue (two laps with the "two clues" option): crew
clues must prove you know the word without handing it to the imposter, and the imposter has to bluff
from the clues so far. Then everyone votes for who they think the imposter is.

- The most votes, alone at the top, puts that player in the spotlight. A tie, or the wrong player, and
  the imposter escapes: +300 to the imposter.
- A caught imposter gets one guess at the word. Right: they steal the round (+200). Wrong: the crew
  wins (+100 each).
- Everyone who voted for the imposter gets +100 either way.

The Undercover twist: the imposter gets a close word instead of nothing ("burger" when the crew have
"pizza") and isn't told they're the imposter. No last guess: if caught, they're caught.

Secrecy: the word goes only to the crew (and the close word only to the imposter); who the imposter is
stays hidden from everyone, TV and audience included, until they are caught or the round ends. Votes
show only who has voted until the count.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError
from .content import IMPOSTER_WORDS
from .drawguess import one_off, squash

ESCAPE, STEAL, CREW_WIN, RIGHT_VOTE = 300, 200, 100, 100
MAX_CLUE, MAX_CLUE_WORDS = 24, 2


def says(text: str, word: str) -> bool:
    """Does `text` say `word` (any case, a plural or two letters of ending allowed)? Whole words only, so
    "cat" doesn't block "category"; a two-word word ("ice cream") counts however it's spaced."""
    w = squash(word)
    if not w:
        return False
    if " " in word.strip():
        return w in squash(text)
    return any(t == w or (t.startswith(w) and len(t) - len(w) <= 2) for t in map(squash, text.split()))


class Imposter(Game):
    game_id: ClassVar[str] = "imposter"
    title: ClassVar[str] = "Imposter"
    blurb: ClassVar[str] = (
        "Everyone gets the secret word except one. Give a clue that proves you know it, then vote out "
        "the faker before they work it out."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8
    OPTIONS: ClassVar[dict[str, list[str]]] = {
        "twist": ["classic", "undercover"],
        "words": ["3", "1", "5"],
        "clues": ["1", "2"],
    }
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone gets the same secret word, except the imposter, who only sees the category.",
        "Take turns to give a one-word clue. Prove you know the word, but don't make it easy!",
        "Then vote for who you think the imposter is. Right vote: +100.",
        "Caught? The imposter gets one guess at the word to steal the round. Escaped: +300 to the imposter.",
        "Undercover twist: the imposter gets a close word instead, and doesn't know they're the imposter.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["cards", "result"])
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"cards": 12.0, "clue": 35.0, "vote": 60.0, "guess": 30.0, "result": 14.0}

    @property
    def undercover(self) -> bool:
        return self.options.get("twist") == "undercover"

    # -- flow -------------------------------------------------------------------------------------------
    def start(self) -> None:
        self.rounds = self.option_int("words")
        self.cards = [IMPOSTER_WORDS[i] for i in self.deal("words", len(IMPOSTER_WORDS), self.rounds)]
        self.history: list[dict[str, Any]] = []
        self.imposter = ""
        self.round = 0
        self._deal()

    def _deal(self) -> None:
        last = self.imposter
        pool = [p for p in self.player_ids if p != last] or list(self.player_ids)
        self.imposter = self.rng.choice(pool)
        order = list(self.player_ids)
        self.rng.shuffle(order)  # anyone may go first, the imposter too: nobody is ruled out
        self.order = order * self.option_int("clues")
        self.clues: list[dict[str, Any]] = []
        self.votes: dict[str, str] = {}
        self.accused: str | None = None
        self.guess: str | None = None
        self.result: dict[str, Any] | None = None
        self.phase = "cards"
        self.set_deadline(self.timings["cards"])
        self.bump()

    @property
    def card(self) -> dict[str, str]:
        return self.cards[min(self.round, self.rounds - 1)]

    def _clue_turn(self) -> None:
        if len(self.clues) >= len(self.order):
            self.phase = "vote"
            self.set_deadline(self.timings["vote"])
        else:
            self.phase = "clue"
            self.set_deadline(self.timings["clue"])
        self.bump()

    @property
    def turn(self) -> str | None:
        return self.order[len(self.clues)] if self.phase == "clue" else None

    def _count(self) -> None:
        tally: dict[str, int] = {}
        for target in self.votes.values():
            tally[target] = tally.get(target, 0) + 1
        top = max(tally.values(), default=0)
        leaders = [p for p, n in tally.items() if n == top]
        self.accused = leaders[0] if top and len(leaders) == 1 else None
        if self.accused == self.imposter and not self.undercover:
            self.phase = "guess"
            self.set_deadline(self.timings["guess"])
            self.bump()
        else:
            self._settle()

    def _settle(self) -> None:
        caught = self.accused == self.imposter
        stole = caught and self.guess is not None and self._matches(self.guess)
        gains = {p: 0 for p in self.player_ids}
        for voter, target in self.votes.items():
            if target == self.imposter:
                gains[voter] += RIGHT_VOTE
        if not caught:
            gains[self.imposter] += ESCAPE
        elif stole:
            gains[self.imposter] += STEAL
        else:
            for p in self.player_ids:
                if p != self.imposter:
                    gains[p] += CREW_WIN
        for p, g in gains.items():
            self.add_points(p, g)
        self.result = {
            "imposter": self.imposter,
            "word": self.card["word"],
            "close": self.card["close"] if self.undercover else None,
            "votes": dict(self.votes),
            "accused": self.accused,
            "caught": caught,
            "guess": self.guess,
            "stole": stole,
            "gains": gains,
        }
        self.history.append({"category": self.card["category"], "clues": list(self.clues), **self.result})
        self.phase = "result"
        self.set_deadline(self.timings["result"])
        self.bump()

    def _matches(self, text: str) -> bool:
        said, word = squash(text), squash(self.card["word"])
        return said == word or (len(word) >= 5 and one_off(said, word))

    def _next(self) -> None:
        if self.round + 1 >= self.rounds:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.round += 1
        self._deal()

    # -- actions ----------------------------------------------------------------------------------------
    def word_for(self, pid: str) -> str | None:
        """The word this player was dealt: the secret word, the close word (Undercover imposter) or none."""
        if pid not in self.round_scores:
            return None
        if pid != self.imposter:
            return self.card["word"]
        return self.card["close"] if self.undercover else None

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "clue":
            self._clue(pid, action.get("text"))
        elif kind == "vote":
            if self.phase != "vote":
                raise GameError("wrong_phase", "Voting isn't open")
            if pid in self.votes:
                raise GameError("already_locked", "You've voted")
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_target", "Vote for another player")
            self.votes[pid] = target
            self.bump()
            if len(self.votes) == len(self.players):
                self._count()
        elif kind == "guess":
            if self.phase != "guess":
                raise GameError("wrong_phase", "No guessing now")
            if pid != self.imposter:
                raise GameError("not_yours", "Only the imposter guesses")
            self.guess = self._text(action.get("text"), MAX_CLUE + 6, "Type the word")
            self._settle()
        else:
            raise GameError("bad_action", "Unknown action")

    @staticmethod
    def _text(raw: Any, limit: int, what: str) -> str:
        if not isinstance(raw, str) or not raw.isprintable():
            raise GameError("bad_input", what)
        text = " ".join(raw.split())
        if not text or len(text) > limit:
            raise GameError("bad_input", f"{what}: 1-{limit} characters")
        return text

    def _clue(self, pid: str, raw: Any) -> None:
        if self.phase != "clue":
            raise GameError("wrong_phase", "It isn't clue time")
        if pid != self.turn:
            raise GameError("not_your_turn", "Wait for your turn")
        text = self._text(raw, MAX_CLUE, "Give a one-word clue")
        if len(text.split()) > MAX_CLUE_WORDS:
            raise GameError("bad_input", "One word (two at most)")
        mine = self.word_for(pid)
        if mine and says(text, mine):
            raise GameError("gives_away", "No saying the word!")
        if any(squash(c["text"]) == squash(text) for c in self.clues if c["text"]):
            raise GameError("taken", "Someone already said that")
        self.clues.append({"by": pid, "text": text})
        self._clue_turn()

    def chat_blocked(self, pid: str, text: str) -> str | None:
        """Typing your word into the chat would hand it to the imposter."""
        if self.phase in ("result", "final"):
            return None
        mine = self.word_for(pid)
        return "No giving the word away!" if mine and says(text, mine) else None

    # -- clocks -----------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "cards":
            self._clue_turn()
        elif self.phase == "clue":
            self.clues.append({"by": self.turn, "text": ""})  # out of time: a pass
            self._clue_turn()
        elif self.phase == "vote":
            self._count()
        elif self.phase == "guess":
            self._settle()
        elif self.phase == "result":
            self._next()

    def skip(self) -> bool:
        """Cards and results only: a skip mid-clue or mid-vote would cut someone short (and a host who is
        the imposter could dodge their guess)."""
        if self.phase not in ("cards", "result"):
            return False
        self.advance()
        return True

    # -- views ------------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        seated = pid in self.round_scores
        over = self.phase in ("result", "final")
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "twist": "undercover" if self.undercover else "classic",
            "category": self.card["category"],
            "order": list(self.order),
            "turn": self.turn,
            "clues": list(self.clues),
            "voted": sorted(self.votes) if self.phase == "vote" else [],
            # In the spotlight: the caught imposter, while they make their guess.
            "accused": self.accused if self.phase == "guess" else None,
            "scores": self.scores(),
            "you": {
                "word": self.word_for(pid),
                # Only a classic imposter is told; the Undercover imposter thinks they're crew.
                "imposter": pid == self.imposter and not self.undercover,
                "vote": self.votes.get(pid),
            }
            if seated
            else None,
        }
        if over and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        escaped = [h for h in self.history if not h["caught"]]
        if escaped:
            h = escaped[0]
            out.append(
                {
                    "icon": "🕵️",
                    "title": "Master of disguise",
                    "text": f"{self.name_of(h['imposter'])} faked their way through “{h['word']}”",
                }
            )
        stolen = next((h for h in self.history if h["stole"]), None)
        if stolen:
            out.append(
                {
                    "icon": "🎯",
                    "title": "Stolen at the buzzer",
                    "text": f"{self.name_of(stolen['imposter'])} was caught but guessed “{stolen['word']}”",
                }
            )
        sharp: dict[str, int] = {}
        for h in self.history:
            for voter, target in h["votes"].items():
                if target == h["imposter"]:
                    sharp[voter] = sharp.get(voter, 0) + 1
        if sharp:
            p, n = max(sharp.items(), key=lambda x: x[1])
            if n >= 2:
                text = f"{self.name_of(p)} spotted {n} imposters"
                out.append({"icon": "🔍", "title": "Sharp eyes", "text": text})
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
