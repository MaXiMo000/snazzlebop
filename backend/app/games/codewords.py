"""Codewords: two teams, 25 words, one secret key. A team game on its own (not part of show nights).

Setup: everyone joins Red or Blue and each team picks a Spymaster (the room starts with balanced random
teams and spymasters, and anyone can switch before the start). The board is 25 words. The key, which
only the two Spymasters see, colours them: 9 for the starting team, 8 for the other, 7 bystanders and
1 assassin.

Turns: the Spymaster gives a one-word clue and a number ("OCEAN 2"). Their team's guessers then reveal
words one at a time, up to the number plus one (a 0 clue means "as many as you like"). A guess on your
own colour lets you keep going; a bystander or the other team's word ends the turn (and helps them).
The assassin loses the game on the spot. Reveal all your team's words first to win.

Guessers can mark words to show teammates what they're thinking before someone taps Reveal. Clues are
the only typed text: one word, letters only, and never a word that's still face down on the board.

Secrecy: the key is in the Spymasters' views only, until each word is revealed (and all of it at the
end). TV and audience screens see what the guessers see.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import CODEWORDS

TEAMS = ("red", "blue")
BOARD = 25
FIRST_COUNT, SECOND_COUNT, NEUTRAL_COUNT = 9, 8, 7
WIN_POINTS = 300
CLUE_RE = re.compile(r"^[A-Z]+(?:-[A-Z]+)?$")
MAX_CLUE = 20
MAX_COUNT = 9


def other(team: str) -> str:
    return "blue" if team == "red" else "red"


class Codewords(Game):
    game_id: ClassVar[str] = "codewords"
    title: ClassVar[str] = "Codewords"
    blurb: ClassVar[str] = (
        "Two teams, 25 words. Your Spymaster gives one-word clues; find your team's words before the "
        "other team does, and never touch the assassin."
    )
    min_players: ClassVar[int] = 4
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False  # a team game: played on its own, not in show nights
    CHAT_MUTED_NOTE: ClassVar[str] = "Spymasters stay silent until the game is over."
    OPTIONS: ClassVar[dict[str, list[str]]] = {"pace": ["relaxed", "speedy"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Two teams, Red and Blue. Each has one Spymaster; everyone else guesses.",
        "Only the Spymasters see which of the 25 words belong to which team.",
        "On your turn your Spymaster gives ONE word and a number, like 'OCEAN 2': two of our words "
        "go with ocean.",
        "Guessers reveal words one at a time (up to the number + 1). Your colour: keep going. A "
        "bystander or the other team's word: turn over.",
        "Reveal all your words first to win. Hit the black assassin and your team loses instantly.",
    )
    READING: ClassVar[frozenset[str]] = frozenset({"teams"})

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"teams": 90.0, "clue": 150.0, "guess": 180.0}

    def start(self) -> None:
        if self.options.get("pace") == "speedy":
            self.timings.update(clue=75.0, guess=90.0)
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        self.teams: dict[str, str] = {pid: TEAMS[i % 2] for i, pid in enumerate(ids)}
        self.spymasters: dict[str, str | None] = {
            t: next(p for p in ids if self.teams[p] == t) for t in TEAMS
        }
        self.words: list[str] = []
        self.key: list[str] = []
        self.revealed: list[bool] = [False] * BOARD
        self.marks: dict[int, list[str]] = {}
        self.log: list[dict[str, Any]] = []  # clues and guesses, public
        self.clue: dict[str, Any] | None = None
        self.guesses_left: int | None = None
        self.guessed_this_turn = 0
        self.turn = self.starting = "red"
        self.winner: str | None = None
        self.how: str = ""  # "words" or "assassin"
        self.round = 0
        self.phase = "teams"
        self.set_deadline(self.timings["teams"])
        self.bump()

    # -- setup ----------------------------------------------------------------
    def _valid_teams(self) -> bool:
        for t in TEAMS:
            members = [p for p, team in self.teams.items() if team == t]
            spy = self.spymasters.get(t)
            if spy not in members or len(members) < 2:
                return False
        return True

    def _fix_teams(self) -> None:
        """Make the setup playable: at least two per team, a spymaster each."""
        for t in TEAMS:
            while sum(1 for v in self.teams.values() if v == t) < 2:
                donors = [
                    p for p, v in self.teams.items() if v == other(t) and p != self.spymasters.get(other(t))
                ]
                self.teams[donors[-1]] = t
        for t in TEAMS:
            members = [p for p in self.player_ids if self.teams[p] == t]
            if self.spymasters.get(t) not in members:
                self.spymasters[t] = members[0]

    def _deal(self) -> None:
        self._fix_teams()
        self.words = [CODEWORDS[i] for i in self.deal("words", len(CODEWORDS), BOARD)]
        self.turn = self.starting = self.rng.choice(TEAMS)  # the starting team gets 9 words
        key = [self.turn] * FIRST_COUNT + [other(self.turn)] * SECOND_COUNT
        key += ["neutral"] * NEUTRAL_COUNT + ["assassin"]
        self.rng.shuffle(key)
        self.key = key
        self._clue_phase()

    def _clue_phase(self) -> None:
        self.clue = None
        self.guesses_left = None
        self.guessed_this_turn = 0
        self.marks = {}
        self.phase = "clue"
        self.set_deadline(self.timings["clue"])
        self.bump()

    def left(self, team: str) -> int:
        return sum(1 for i, k in enumerate(self.key) if k == team and not self.revealed[i])

    # -- actions --------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if self.phase == "teams":
            self._setup_action(pid, kind, action)
        elif self.phase == "clue":
            if kind != "clue":
                raise GameError("wrong_phase", "Waiting for the Spymaster's clue")
            self._give_clue(pid, action)
        elif self.phase == "guess":
            self._guess_action(pid, kind, action)
        else:
            raise GameError("wrong_phase", "The game is over")

    def _setup_action(self, pid: str, kind: Any, action: dict[str, Any]) -> None:
        if kind == "team":
            team = action.get("team")
            if team not in TEAMS:
                raise GameError("bad_input", "Red or Blue?")
            old = self.teams[pid]
            if old != team and self.spymasters.get(old) == pid:
                self.spymasters[old] = None
            self.teams[pid] = team
        elif kind == "spymaster":
            team = self.teams[pid]
            self.spymasters[team] = pid
        else:
            raise GameError("bad_action", "Pick a team or become the Spymaster")
        self.bump()

    def _give_clue(self, pid: str, action: dict[str, Any]) -> None:
        if pid != self.spymasters.get(self.turn):
            raise GameError("not_spymaster", "Only this team's Spymaster gives the clue")
        raw = action.get("word")
        if not isinstance(raw, str):
            raise GameError("bad_input", "One word, please")
        word = unicodedata.normalize("NFKC", raw).strip().upper()
        if not 1 <= len(word) <= MAX_CLUE or not CLUE_RE.match(word):
            raise GameError("bad_input", "One word, letters only")
        for i, w in enumerate(self.words):
            if not self.revealed[i] and (word == w or word in w or w in word):
                raise GameError("bad_clue", "Your clue can't be (or contain) a word on the board")
        count = as_int(action.get("count"), lo=0, hi=MAX_COUNT, field="Number")
        self.clue = {"team": self.turn, "word": word, "count": count}
        self.guesses_left = None if count == 0 else count + 1
        self.log.append({"type": "clue", **self.clue})
        self.phase = "guess"
        self.set_deadline(self.timings["guess"])
        self.bump()

    def _guesser(self, pid: str) -> None:
        if self.teams.get(pid) != self.turn:
            raise GameError("not_your_turn", "It's the other team's turn")
        if pid == self.spymasters.get(self.turn):
            raise GameError("spymaster", "Spymasters can't guess")

    def _card(self, action: dict[str, Any]) -> int:
        i = as_int(action.get("card"), lo=0, hi=BOARD - 1, field="Card")
        if self.revealed[i]:
            raise GameError("revealed", "That word is already revealed")
        return i

    def _guess_action(self, pid: str, kind: Any, action: dict[str, Any]) -> None:
        self._guesser(pid)
        if kind == "mark":
            i = self._card(action)
            who = self.marks.setdefault(i, [])
            if pid in who:
                who.remove(pid)
            else:
                who.append(pid)
            if not who:
                del self.marks[i]
            self.bump()
        elif kind == "reveal":
            self._reveal(pid, self._card(action))
        elif kind == "pass":
            if self.guessed_this_turn == 0:
                raise GameError("guess_first", "Make at least one guess before ending the turn")
            self.log.append({"type": "pass", "team": self.turn, "by": pid})
            self._end_turn()
        else:
            raise GameError("bad_action", "Unknown action")

    def _reveal(self, pid: str, i: int) -> None:
        self.revealed[i] = True
        self.marks.pop(i, None)
        color = self.key[i]
        self.guessed_this_turn += 1
        self.log.append(
            {"type": "guess", "team": self.turn, "by": pid, "card": i, "word": self.words[i], "color": color}
        )
        if color == "assassin":
            self._finish(other(self.turn), "assassin")
            return
        for t in TEAMS:
            if self.left(t) == 0:
                self._finish(t, "words")
                return
        if color != self.turn:
            self._end_turn()
            return
        if self.guesses_left is not None:
            self.guesses_left -= 1
            if self.guesses_left == 0:
                self._end_turn()
                return
        self.bump()

    def _end_turn(self) -> None:
        self.turn = other(self.turn)
        self.round += 1
        self._clue_phase()

    def _finish(self, winner: str, how: str) -> None:
        self.winner, self.how = winner, how
        for pid, team in self.teams.items():
            if team == winner:
                self.add_points(pid, WIN_POINTS)
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- clocks ---------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        """Timer or host: setup starts the game; a silent Spymaster or slow team loses the turn."""
        if self.finished:
            return
        if self.phase == "teams":
            self._deal()
        elif self.phase == "clue":
            self.log.append({"type": "timeout", "team": self.turn})
            self._end_turn()
        elif self.phase == "guess":
            self._end_turn()

    # -- views ----------------------------------------------------------------
    def chat_team(self, pid: str) -> tuple[str, str] | None:
        team = self.teams.get(pid)
        return None if team is None else (f"team:{team}", f"{team.capitalize()} team")

    def chat_muted(self, pid: str) -> bool:
        """Spymasters say nothing but their clue (the official rule), in any chat."""
        return self.phase in ("clue", "guess") and pid in self.spymasters.values()

    def view_for(self, pid: str) -> dict[str, Any]:
        team = self.teams.get(pid)
        spy = team is not None and self.spymasters.get(team) == pid
        show_key = self.finished or (spy and self.phase != "teams")
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": 0,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "teams": dict(self.teams),
            "spymasters": dict(self.spymasters),
            "turn": self.turn,
            "board": [
                {
                    "word": w,
                    "revealed": self.revealed[i],
                    # a revealed word's colour is public; the rest only for Spymasters (and at the end)
                    "color": self.key[i] if self.revealed[i] or show_key else None,
                    "marks": list(self.marks.get(i, [])),
                }
                for i, w in enumerate(self.words)
            ],
            "left": {t: self.left(t) for t in TEAMS} if self.words else {t: 0 for t in TEAMS},
            "starting": self.starting if self.words else None,
            "clue": dict(self.clue) if self.clue else None,
            "guesses_left": self.guesses_left,
            "guessed_this_turn": self.guessed_this_turn,
            "log": self.log[-30:],
            "pace": self.options.get("pace", "relaxed"),
            "you": {"team": team, "spymaster": spy},
            "valid_teams": self._valid_teams(),
        }
        if self.finished:
            view["winner"] = self.winner
            view["how"] = self.how
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished or not self.winner:
            return []
        loser = other(self.winner)
        names = lambda t: ", ".join(self.name_of(p) for p, v in self.teams.items() if v == t)  # noqa: E731
        out = [
            {
                "icon": "🏆",
                "title": f"{self.winner.title()} team wins",
                "text": names(self.winner),
            }
        ]
        if self.how == "assassin":
            hit = next(e for e in reversed(self.log) if e["type"] == "guess" and e["color"] == "assassin")
            out.append(
                {
                    "icon": "☠️",
                    "title": "Assassinated",
                    "text": f"{self.name_of(hit['by'])} ({loser}) found the assassin: {hit['word']}",
                }
            )
        # The best clue: the most words of its team found straight after it.
        best: tuple[int, dict[str, Any]] | None = None
        current: dict[str, Any] | None = None
        hits = 0
        for e in [*self.log, {"type": "end"}]:
            if e["type"] in ("clue", "end", "pass", "timeout"):
                if current and hits >= 2 and (best is None or hits > best[0]):
                    best = (hits, current)
                current, hits = (e if e["type"] == "clue" else None), 0
            elif e["type"] == "guess" and current and e["color"] == current["team"]:
                hits += 1
        if best:
            hits, c = best
            spy = self.spymasters.get(c["team"])
            out.append(
                {
                    "icon": "🧠",
                    "title": "Mind meld",
                    "text": f"{self.name_of(spy or '')}'s clue {c['word']} found {hits} words",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "how": self.how,
            "clues": sum(e["type"] == "clue" for e in self.log),
        }
