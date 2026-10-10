"""Mafia Night: the classic hidden-role game of nights and days.

Everyone is dealt a secret role. At night the Mafia quietly choose someone to remove, the Detective
checks whether one player is Mafia, and the Doctor protects one player. Villagers tap a suspect too (it
changes nothing, but it means every phone is busy, so nobody can tell who has a job). In the morning the
room learns who was lost, talks it over, and votes someone out. A removed player's role is shown.

The town wins when every Mafia member is out; the Mafia win when they are at least half of the players
left. Roles, night choices and the Detective's findings live on the server and reach only the people the
rules say may know them. Removed players become ghosts: they see every role but can no longer chat.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from .base import Game, GameError

MAFIA, DETECTIVE, DOCTOR, VILLAGER = "mafia", "detective", "doctor", "villager"
ROLE_NAME = {MAFIA: "Mafia", DETECTIVE: "Detective", DOCTOR: "Doctor", VILLAGER: "Villager"}
WIN, SURVIVE, KILL, FOUND, SAVE, GOOD_VOTE = 300, 100, 100, 100, 150, 50
MAX_ROUNDS = 12  # a safety net: no game of eight can run this long


def roles_for(n: int) -> list[str]:
    """One Mafia up to six players, two from seven; a Detective always; a Doctor from five."""
    roles = [MAFIA] * (2 if n >= 7 else 1) + [DETECTIVE] + ([DOCTOR] if n >= 5 else [])
    return roles + [VILLAGER] * (n - len(roles))


class MafiaNight(Game):
    game_id: ClassVar[str] = "mafia"
    title: ClassVar[str] = "Mafia Night"
    blurb: ClassVar[str] = (
        "Secret roles, quiet nights and loud days. The Mafia remove someone each night; "
        "the town talks it over and votes someone out. Find them before they outnumber you."
    )
    min_players: ClassVar[int] = 4
    max_players: ClassVar[int] = 8
    OPTIONS: ClassVar[dict[str, list[str]]] = {"day": ["90", "60", "120", "180"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone gets a secret role: Mafia, Detective, Doctor or Villager. Keep it to yourself.",
        "NIGHT: the Mafia pick someone to remove. The Detective checks one player. The Doctor protects one.",
        "Villagers tap a suspect too, so every phone looks busy and nobody can tell who has a job.",
        "DAY: talk it over (the call helps), then vote someone out. A tie or a skip means nobody goes.",
        "Town wins when all Mafia are out. Mafia win when they are half of the players left.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["roles", "dawn", "verdict"])
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    CHAT_MUTED_NOTE: ClassVar[str] = "Ghosts can't talk to the living."

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"roles": 15.0, "night": 45.0, "dawn": 12.0, "verdict": 12.0}

    # -- setup ----------------------------------------------------------------------------------------
    def start(self) -> None:
        ids = self.player_ids
        dealt = roles_for(len(ids))
        self.rng.shuffle(dealt)
        self.roles: dict[str, str] = dict(zip(ids, dealt, strict=True))
        self.alive: list[str] = list(ids)
        self.dead: list[dict[str, Any]] = []  # in order: {id, role, how: "night" | "vote", round}
        self.day_seconds = float(self.options.get("day", "90"))
        self.picks: dict[str, str] = {}  # tonight's choices, by player
        self.votes: dict[str, str | None] = {}  # today's votes (None = skip)
        self.findings: dict[str, bool] = {}  # the Detective's results: player -> is Mafia
        self.last_protected: str | None = None
        self.news: dict[str, Any] = {}  # what the last dawn or verdict announced
        self.log: list[dict[str, Any]] = []
        self.winner: str | None = None  # "town" | "mafia"
        self.round = 1
        self.phase = "roles"
        self.set_deadline(self.timings["roles"])
        self.bump()

    def _mafia(self) -> list[str]:
        return [p for p in self.alive if self.roles[p] == MAFIA]

    def _holder(self, role: str) -> str | None:
        return next((p for p in self.alive if self.roles[p] == role), None)

    def _night(self) -> None:
        self.picks = {}
        self.news = {}
        self.phase = "night"
        self.set_deadline(self.timings["night"])
        self.bump()

    def _day(self) -> None:
        self.votes = {}
        self.phase = "day"
        self.set_deadline(self.day_seconds)
        self.bump()

    def _remove(self, pid: str, how: str) -> None:
        self.alive.remove(pid)
        self.dead.append({"id": pid, "role": self.roles[pid], "how": how, "round": self.round})

    def _over(self) -> bool:
        mafia = len(self._mafia())
        if mafia == 0:
            self.winner = "town"
        elif mafia * 2 >= len(self.alive) or self.round >= MAX_ROUNDS:
            self.winner = "mafia"
        else:
            return False
        for pid, role in self.roles.items():
            if (role == MAFIA) == (self.winner == "mafia"):
                self.add_points(pid, WIN)
            if pid in self.alive:
                self.add_points(pid, SURVIVE)
        return True

    def _finish(self) -> None:
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- resolving ------------------------------------------------------------------------------------
    def _end_night(self) -> None:
        mafia = self._mafia()
        wanted = Counter(self.picks[m] for m in mafia if m in self.picks)
        target = None
        if wanted:
            top = max(wanted.values())
            target = self.rng.choice(sorted(t for t, c in wanted.items() if c == top))
        doctor, detective = self._holder(DOCTOR), self._holder(DETECTIVE)
        protected = self.picks.get(doctor) if doctor else None
        checked = self.picks.get(detective) if detective else None
        if detective and checked:
            self.findings[checked] = self.roles[checked] == MAFIA
            if self.findings[checked]:
                self.add_points(detective, FOUND)
        saved = target is not None and target == protected
        killed = None if saved else target
        if saved and doctor:
            self.add_points(doctor, SAVE)
        self.last_protected = protected
        if killed:
            self._remove(killed, "night")
            for m in mafia:
                self.add_points(m, KILL)
        self.news = {
            "kind": "dawn",
            "killed": killed,
            "saved": saved,
            "role": self.roles[killed] if killed else None,
        }
        self.log.append(
            {"round": self.round, "kind": "night", "killed": killed, "saved": saved, "checked": checked}
        )
        self.phase = "dawn"
        self.set_deadline(self.timings["dawn"])
        self.bump()

    def _end_day(self) -> None:
        tally = Counter(t for t in self.votes.values() if t is not None)
        skips = sum(t is None for t in self.votes.values())
        out = None
        if tally:
            (first, most), *rest = tally.most_common()
            if most > skips and (not rest or rest[0][1] < most):
                out = first
        if out:
            if self.roles[out] == MAFIA:
                for voter, t in self.votes.items():
                    if t == out and self.roles[voter] != MAFIA:
                        self.add_points(voter, GOOD_VOTE)
            self._remove(out, "vote")
        self.news = {
            "kind": "verdict",
            "out": out,
            "role": self.roles[out] if out else None,
            "votes": dict(self.votes),
        }
        self.log.append({"round": self.round, "kind": "day", "out": out, "votes": dict(self.votes)})
        self.phase = "verdict"
        self.set_deadline(self.timings["verdict"])
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def _target(self, pid: str, raw: Any) -> str:
        if not isinstance(raw, str) or raw not in self.alive:
            raise GameError("bad_target", "Pick someone who is still in the game")
        if raw == pid and not (self.phase == "night" and self.roles[pid] == DOCTOR):
            raise GameError("bad_target", "Pick someone else")
        return raw

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind not in ("night", "vote"):
            raise GameError("bad_action", "Unknown action")
        if pid not in self.alive:
            raise GameError("out", "Ghosts only watch")
        if kind == "night":
            if self.phase != "night":
                raise GameError("wrong_phase", "It isn't night")
            target = self._target(pid, action.get("target"))
            role = self.roles[pid]
            if role == MAFIA and self.roles[target] == MAFIA:
                raise GameError("bad_target", "Not one of your own")
            if role == DOCTOR and target == self.last_protected:
                raise GameError("bad_target", "You can't protect the same person two nights running")
            self.picks[pid] = target
            self.bump()
            if all(p in self.picks for p in self.alive):
                self._end_night()
        else:
            if self.phase != "day":
                raise GameError("wrong_phase", "Voting happens in the day")
            raw = action.get("target")
            self.votes[pid] = None if raw is None else self._target(pid, raw)
            self.bump()
            if all(p in self.votes for p in self.alive):
                self._end_day()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "roles":
            self._night()
        elif self.phase == "night":
            self._end_night()
        elif self.phase == "dawn":
            self._finish() if self._over() else self._day()
        elif self.phase == "day":
            self._end_day()
        elif self.phase == "verdict":
            if self._over():
                self._finish()
            else:
                self.round += 1
                self._night()

    # -- chat -----------------------------------------------------------------------------------------
    def chat_team(self, pid: str) -> tuple[str, str] | None:
        """The Mafia's private channel (only while there are at least two of them to talk)."""
        if self.finished or self.roles.get(pid) != MAFIA or pid not in self.alive:
            return None
        return ("mafia", "Mafia") if sum(r == MAFIA for r in self.roles.values()) > 1 else None

    def chat_muted(self, pid: str) -> bool:
        return not self.finished and pid in self.roles and pid not in self.alive

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        role = self.roles.get(pid)
        ghost = role is not None and pid not in self.alive
        open_book = self.phase == "final" or ghost  # everything is on the table for ghosts and at the end
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "alive": list(self.alive),
            "dead": list(self.dead),
            "counts": dict(Counter(self.roles.values())),  # how many of each role were dealt (public)
            "acted": sorted(self.picks) if self.phase == "night" else [],  # who, never what
            "votes": dict(self.votes) if self.phase == "day" else {},
            "news": self.news if self.phase in ("dawn", "verdict") else None,
            "winner": self.winner if self.phase == "final" else None,
            "roles": dict(self.roles) if open_book else None,
            "you": None,
        }
        if role is not None:
            mates = [p for p, r in self.roles.items() if r == MAFIA and p != pid] if role == MAFIA else []
            you: dict[str, Any] = {
                "role": role,
                "alive": not ghost,
                "mates": mates,
                "pick": self.picks.get(pid) if self.phase == "night" else None,
                "vote": self.votes.get(pid) if self.phase == "day" else None,
                "voted": pid in self.votes if self.phase == "day" else False,
            }
            if role == MAFIA and self.phase == "night":
                you["mate_picks"] = {m: self.picks[m] for m in mates if m in self.picks}
            if role == DETECTIVE:
                you["findings"] = dict(self.findings)
            if role == DOCTOR:
                you["last_protected"] = self.last_protected
            view["you"] = you
        if self.phase == "final":
            view["log"] = self.log
            view["scores"] = self.scores()
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out = [
            {
                "icon": "🕵️" if self.winner == "town" else "🎩",
                "title": "Town wins" if self.winner == "town" else "Mafia win",
                "text": (
                    "The town found every Mafia member"
                    if self.winner == "town"
                    else "The Mafia took over: "
                    + " & ".join(self.name_of(p) for p, r in self.roles.items() if r == MAFIA)
                ),
            }
        ]
        saves = sum(1 for e in self.log if e["kind"] == "night" and e["saved"])
        doctor = next((p for p, r in self.roles.items() if r == DOCTOR), None)
        if saves and doctor:
            out.append(
                {"icon": "🩺", "title": "Night shift", "text": f"{self.name_of(doctor)} saved {saves}"}
            )
        wrong = [
            e["out"] for e in self.log if e["kind"] == "day" and e["out"] and self.roles[e["out"]] != MAFIA
        ]
        if wrong:
            out.append(
                {
                    "icon": "🙈",
                    "title": "Oops",
                    "text": f"The town voted out innocent {self.name_of(wrong[0])}",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "winner": self.winner, "rounds": self.round}
