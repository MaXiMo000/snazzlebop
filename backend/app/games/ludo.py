"""Ludo: the classic race-and-capture board game.

Board: a 52-square track around a cross, four yards in the corners and a five-square home column per
colour leading to the centre. Each colour has four tokens (two in the quick game), all in the yard.

Your turn: roll the die. A 6 brings a token out onto your start square (or moves one already out).
Move one token forward exactly the number rolled. Land on a lone or stacked rival token and it goes
back to its yard, unless the square is safe: the four start squares and the four stars. Tokens must
reach the centre by exact count.

Roll again after a 6, a capture, or bringing a token home. Three 6s in a row and the turn is lost.
The first colour with every token home wins; play goes on for 2nd and 3rd place (finished colours are
skipped) until only one colour is left.

Players: one colour each with 2-4 (two players sit opposite). With 5-8, teams of two share a colour and
take turns rolling for it; everything a colour scores goes to every player in it.
Scoring: 100 per token home, 50 per capture; 500 for 1st place, 300 for 2nd, 150 for 3rd.

Ludo has no secrets: every view is the same apart from whose colour is yours.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

COLORS = ("red", "green", "yellow", "blue")  # clockwise; turn order follows the track
TRACK = 52
START = {"red": 0, "green": 13, "yellow": 26, "blue": 39}  # absolute square of each start
SAFE = frozenset({0, 8, 13, 21, 26, 34, 39, 47})  # starts and stars
LAST_TRACK = 50  # relative square before the home column
HOME = 56  # relative 51-55 = home column, 56 = home
YARD = -1
TURN_SECONDS = 20.0
HOME_POINTS = 100
CAPTURE_POINTS = 50
PLACE_POINTS = (500, 300, 150)  # 1st, 2nd, 3rd; the last colour home gets none


def colors_for(n: int) -> tuple[str, ...]:
    """Two players sit opposite; five or more share colours in pairs."""
    if n == 2:
        return ("red", "yellow")
    if n >= 5:
        n = (n + 1) // 2
    return COLORS[:n]


def square(color: str, pos: int) -> int | None:
    """The absolute track square of a relative position (None in the yard, home column or home)."""
    if 0 <= pos <= LAST_TRACK:
        return (START[color] + pos) % TRACK
    return None


class Ludo(Game):
    game_id: ClassVar[str] = "ludo"
    title: ClassVar[str] = "Ludo"
    blurb: ClassVar[str] = (
        "The race round the cross everyone grew up with: roll a six to get out, knock rivals back to "
        "their yard, bring all your tokens home first."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"tokens": ["4", "2"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Roll the die. You need a 6 to bring a token out of your yard onto your start square.",
        "Move one token forward by the roll. Land on a rival and they go back to their yard, except on "
        "start squares and stars, which are safe.",
        "Roll again after a 6, a capture or a token reaching home. Three 6s in a row and you lose the turn.",
        "Tokens go round the board, up your colour's home column and into the centre by exact count.",
        "First colour with every token home wins; play goes on for 2nd and 3rd place. With 5 or more "
        "players, teams of two share a colour.",
    )

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"turn": TURN_SECONDS}

    # -- setup ----------------------------------------------------------------------------------------
    def start(self) -> None:
        self.n_tokens = 2 if self.options.get("tokens") == "2" else 4
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        self.colors: tuple[str, ...] = colors_for(len(ids))
        self.members: dict[str, list[str]] = {c: [] for c in self.colors}
        for i, pid in enumerate(ids):
            self.members[self.colors[i % len(self.colors)]].append(pid)
        self.color_of = {p: c for c, ps in self.members.items() for p in ps}
        self.tokens: dict[str, list[int]] = {c: [YARD] * self.n_tokens for c in self.colors}
        self.points: dict[str, int] = dict.fromkeys(self.colors, 0)
        self.rota: dict[str, int] = dict.fromkeys(self.colors, 0)  # whose go it is within a team
        self.stats: dict[str, dict[str, int]] = {
            p: {"captures": 0, "captured": 0, "sixes": 0, "busts": 0} for p in self.player_ids
        }
        self.turn = 0
        self.rolled: int | None = None
        self.sixes = 0
        self.seq = 0
        self.log: list[dict[str, Any]] = []
        self.winner: str | None = None
        self.places: list[str] = []  # colours in the order they got every token home
        self.phase = "play"
        self.set_deadline(self.timings["turn"])
        self.bump()

    # -- helpers --------------------------------------------------------------------------------------
    @property
    def color(self) -> str:
        return self.colors[self.turn]

    @property
    def current(self) -> str:
        team = self.members[self.color]
        return team[self.rota[self.color] % len(team)]

    def _log(self, entry: dict[str, Any]) -> None:
        self.seq += 1
        self.log.append({"n": self.seq, **entry})

    def legal(self, color: str, roll: int) -> list[int]:
        """Tokens that can move this roll."""
        out = []
        for i, pos in enumerate(self.tokens[color]):
            if pos == YARD:
                if roll == 6:
                    out.append(i)
            elif pos + roll <= HOME:
                out.append(i)
        return out

    def _score(self, color: str, pts: int) -> None:
        self.points[color] += pts
        for p in self.members[color]:
            self.add_points(p, pts)

    def _actor(self, pid: str) -> None:
        if self.phase != "play":
            raise GameError("wrong_phase", "The game is over")
        if pid != self.current:
            raise GameError("not_your_turn", "It's not your turn")

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "roll":
            self._actor(pid)
            self._roll()
        elif kind == "move":
            self._actor(pid)
            if self.rolled is None:
                raise GameError("roll_first", "Roll the die first")
            token = as_int(action.get("token"), lo=0, hi=self.n_tokens - 1, field="Token")
            if token not in self.legal(self.color, self.rolled):
                raise GameError("cant_move", "That token can't move")
            self._move(token)
        else:
            raise GameError("bad_action", "Unknown action")
        self.bump()

    def _roll(self) -> None:
        if self.rolled is not None:
            raise GameError("already_rolled", "Move a token first")
        roll = self.rng.randint(1, 6)
        color, pid = self.color, self.current
        self._log({"type": "roll", "color": color, "player": pid, "value": roll})
        if roll != 6:
            self.sixes = 0
        else:
            self.sixes += 1
            self.stats[pid]["sixes"] += 1
            if self.sixes == 3:
                self.stats[pid]["busts"] += 1
                self._log({"type": "bust", "color": color, "player": pid})
                self._end_turn(bonus=False)
                return
        self.rolled = roll
        moves = self.legal(color, roll)
        if not moves:
            self._log({"type": "stuck", "color": color, "player": pid})
            self._end_turn(bonus=roll == 6)
            return
        # One real choice (e.g. every movable token still in the yard): move it straight away.
        if len({self.tokens[color][i] for i in moves}) == 1:
            self._move(moves[0])
        else:
            self.set_deadline(self.timings["turn"])

    def _move(self, token: int) -> None:
        color, pid, roll = self.color, self.current, self.rolled
        if roll is None:  # guarded by the callers; keeps the type checker honest
            return
        start = self.tokens[color][token]
        to = 0 if start == YARD else start + roll
        self.tokens[color][token] = to
        self.rolled = None
        self._log({"type": "move", "color": color, "player": pid, "token": token, "from": start, "to": to})
        bonus = roll == 6
        sq = square(color, to)
        if sq is not None and sq not in SAFE:
            victims = [
                {"color": c, "token": i}
                for c in self.colors
                if c != color
                for i, pos in enumerate(self.tokens[c])
                if square(c, pos) == sq
            ]
            for v in victims:
                self.tokens[v["color"]][v["token"]] = YARD
                for p in self.members[v["color"]]:
                    self.stats[p]["captured"] += 1
            if victims:
                self.stats[pid]["captures"] += len(victims)
                self._score(color, CAPTURE_POINTS * len(victims))
                self._log({"type": "capture", "color": color, "player": pid, "victims": victims})
                bonus = True
        if to == HOME:
            self._score(color, HOME_POINTS)
            self._log({"type": "home", "color": color, "player": pid, "token": token})
            bonus = True
            if all(p == HOME for p in self.tokens[color]):
                self._place(color)
                if not self.finished:
                    self._end_turn(bonus=False)  # done: no more rolls for this colour
                return
        self._end_turn(bonus)

    def _end_turn(self, bonus: bool) -> None:
        self.rolled = None
        if bonus:
            self._log({"type": "again", "color": self.color, "player": self.current})
        else:
            self.sixes = 0
            self.rota[self.color] += 1
            self.turn = (self.turn + 1) % len(self.colors)
            while self.color in self.places:  # finished colours sit out
                self.turn = (self.turn + 1) % len(self.colors)
        self.set_deadline(self.timings["turn"])

    def _place(self, color: str) -> None:
        """Every token home: 1st, 2nd or 3rd. The game ends when one colour is left racing."""
        self.places.append(color)
        n = len(self.places)
        pts = PLACE_POINTS[n - 1] if n <= len(PLACE_POINTS) else 0
        self._score(color, pts)
        if n == 1:
            self.winner = color
        self._log({"type": "place", "color": color, "place": n, "points": pts})
        left = [c for c in self.colors if c not in self.places]
        if len(left) <= 1:
            self.places.extend(left)  # the last colour still racing comes last
            self.rolled = None
            self.phase = "final"
            self.deadline = None
            self.finished = True

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        """Timer or host: roll for a silent player and move their furthest token."""
        if self.finished:
            return
        self._log({"type": "timeout", "color": self.color, "player": self.current})
        if self.rolled is None:
            self._roll()
        if self.rolled is not None and not self.finished:
            moves = self.legal(self.color, self.rolled)
            self._move(max(moves, key=lambda i: self.tokens[self.color][i]))
        self.bump()

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        playing = self.phase == "play"
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": 1,
            "rounds": 1,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "teams": [
                {
                    "color": c,
                    "members": list(self.members[c]),
                    "tokens": list(self.tokens[c]),
                    "points": self.points[c],
                }
                for c in self.colors
            ],
            "turn_color": self.color if playing else None,
            "turn": self.current if playing else None,
            "rolled": self.rolled,
            "sixes": self.sixes,
            "movable": self.legal(self.color, self.rolled) if playing and self.rolled is not None else [],
            "log": self.log[-14:],
            "you": self.color_of.get(pid),
            "winner": self.winner,
            "places": list(self.places),
            "scores": self.scores(),
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        if self.winner:
            names = " & ".join(self.name_of(p) for p in self.members[self.winner])
            out.append({"icon": "🏁", "title": "Home and dry", "text": f"{names} got every token home first"})
        bully = max(self.player_ids, key=lambda p: self.stats[p]["captures"])
        if self.stats[bully]["captures"] >= 2:
            n = self.stats[bully]["captures"]
            out.append(
                {"icon": "💥", "title": "Bully", "text": f"{self.name_of(bully)} sent {n} tokens home"}
            )
        bust = max(self.player_ids, key=lambda p: self.stats[p]["busts"])
        if self.stats[bust]["busts"]:
            out.append(
                {"icon": "🎲", "title": "Too hot", "text": f"{self.name_of(bust)} rolled three 6s in a row"}
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "colors": len(self.colors),
            "tokens": self.n_tokens,
            "places": len(self.places),
        }
