"""Mole in the Mural: a hidden-role game with no free text.

A mural of 16 tiles hides one secret "painting". Every player knows which tile it is, except the
Mole (two Moles at 7-8 players, who don't know about each other). Over two hint rounds everyone
secretly picks one tile as a hint; hints are revealed together at the end of each round. Innocents'
hints must share a colour or a kind with the painting (the server enforces it). A Mole doesn't know
the painting, so has to bluff from what others pick, and may pull one Switcheroo: their hint and
another player's swap places in that round's public reveal. Then the room votes; the k most-voted
players (k = number of Moles) are accused. A caught Mole gets one guess at the painting to steal.

Secrecy: the painting never reaches a Mole or a TV screen before the end; nobody sees anyone else's
hint before the round reveal; each Mole is told only that they are one. A Mole's hints are never
validated: rejecting one would tell them where the painting is. Who swapped is secret until the end.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import MURAL_TILES

TILES = 16
HINT_ROUNDS = 2
TWO_MOLES_FROM = 7  # players


def _related(a: dict[str, str], b: dict[str, str]) -> bool:
    return a["color"] == b["color"] or a["kind"] == b["kind"]


class MoleInTheMural(Game):
    game_id: ClassVar[str] = "mural"
    title: ClassVar[str] = "Mole in the Mural"
    blurb: ClassVar[str] = (
        "Everyone knows which tile is the secret painting - except the Mole. "
        "Drop hints, spot the bluffer, vote. A caught Mole gets one guess to steal the win."
    )
    min_players: ClassVar[int] = 4
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"briefing": 20.0, "hint": 40.0, "vote": 40.0, "mole_guess": 25.0}

    # -- setup --------------------------------------------------------------
    def start(self) -> None:
        rng = self.rng
        painting = MURAL_TILES[self.deal("paintings", len(MURAL_TILES), 1, kind="mural")[0]]
        others = [t for t in MURAL_TILES if t is not painting]
        related = [t for t in others if _related(t, painting)]
        unrelated = [t for t in others if not _related(t, painting)]
        # Enough related tiles that every innocent has real choices for both rounds,
        # enough unrelated ones that a bluffing Mole can slip up.
        n_related = min(len(related), rng.randint(5, 7))
        tiles = rng.sample(related, n_related) + rng.sample(unrelated, TILES - 1 - n_related) + [painting]
        rng.shuffle(tiles)
        self.mural: list[dict[str, str]] = tiles
        self.target = tiles.index(painting)
        n_moles = 2 if len(self.players) >= TWO_MOLES_FROM else 1
        self.moles: list[str] = rng.sample(self.player_ids, n_moles)
        self.hints: list[dict[str, int]] = []  # revealed rounds only, as shown (after any swap)
        self.played: dict[str, list[int]] = {}  # what each player really hinted, round by round
        self.current: dict[str, int] = {}
        self.swaps: list[dict[str, Any]] = []  # {"round", "by", "with", "done"}: secret until the end
        self.votes: dict[str, str] = {}
        self.caught: list[str] = []
        self.guesses: dict[str, int] = {}
        self.result: dict[str, Any] | None = None
        self.round = 0
        self._enter("briefing")

    def _enter(self, phase: str) -> None:
        self.phase = phase
        self.set_deadline(self.timings[phase])
        self.bump()

    def _pending_swap(self, pid: str) -> dict[str, Any] | None:
        return next((s for s in self.swaps if s["by"] == pid and s["round"] == self.round), None)

    def _close_hint_round(self) -> None:
        for pid, tile in self.current.items():
            self.played.setdefault(pid, []).append(tile)
        shown = dict(self.current)
        for s in self.swaps:
            if s["round"] == self.round and s["by"] in shown and s["with"] in shown:
                a, b = s["by"], s["with"]
                shown[a], shown[b] = shown[b], shown[a]
                s["done"] = True
        self.hints.append(shown)
        self.current = {}
        if len(self.hints) < HINT_ROUNDS:
            self.round += 1
            self._enter("hint")
        else:
            self._enter("vote")

    def _close_vote(self) -> None:
        """The k most-voted are accused (k = number of Moles); a tie at the cut-off accuses nobody there."""
        ranked = Counter(self.votes.values()).most_common()
        k = len(self.moles)
        next_count = ranked[k][1] if len(ranked) > k else 0
        accused = [p for p, c in ranked[:k] if c > next_count]
        self.caught = [p for p in accused if p in self.moles]
        if self.caught:
            self._enter("mole_guess")
        else:
            self._finish()

    def _finish(self) -> None:
        k = len(self.moles)
        stole = [m for m in self.caught if self.guesses.get(m) == self.target]
        missed = [m for m in self.caught if m not in stole]
        for m in self.moles:
            if m not in self.caught:
                self.add_points(m, 300)
            elif m in stole:
                self.add_points(m, 200)
        if missed:
            for pid in self.player_ids:
                if pid not in self.moles:
                    self.add_points(
                        pid, 150 * len(missed) // k + (50 if self.votes.get(pid) in self.moles else 0)
                    )
        self.result = {
            "moles": list(self.moles),
            "target": self.target,
            "caught": list(self.caught),
            "guesses": dict(self.guesses),
            "stole": stole,
            "tally": dict(Counter(self.votes.values())),
            "votes": dict(self.votes),
            "swaps": [dict(s) for s in self.swaps if s["done"]],
        }
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- actions ------------------------------------------------------------
    def _tile(self, action: dict[str, Any]) -> int:
        return as_int(action.get("tile"), lo=0, hi=TILES - 1, field="Tile")

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "hint":
            if self.phase != "hint":
                raise GameError("wrong_phase", "Hints are closed")
            if pid in self.current:
                raise GameError("already_locked", "Your hint is already in")
            tile = self._tile(action)
            # Their own earlier hints, not the public record: a Switcheroo may have swapped that.
            if tile in self.played.get(pid, []):
                raise GameError("bad_input", "Pick a tile you haven't used yet")
            if pid not in self.moles:  # never validate a Mole: a refusal would point at the painting
                if tile == self.target:
                    raise GameError("bad_input", "That's the painting itself! Hint at it instead")
                if not _related(self.mural[tile], self.mural[self.target]):
                    raise GameError("bad_input", "Hints must share a colour or a kind with the painting")
            self.current[pid] = tile
            self.bump()
            if len(self.current) == len(self.players):
                self._close_hint_round()
        elif kind == "swap":
            if self.phase != "hint":
                raise GameError("wrong_phase", "Swaps happen during a hint round")
            if pid not in self.moles:
                raise GameError("not_mole", "Only a Mole can do that")
            if any(s["by"] == pid for s in self.swaps):
                raise GameError("swap_used", "You've already used your Switcheroo")
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_input", "Pick another player")
            self.swaps.append({"round": self.round, "by": pid, "with": target, "done": False})
            self.bump()
        elif kind == "vote":
            if self.phase != "vote":
                raise GameError("wrong_phase", "Voting isn't open")
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_input", "Vote for another player")
            self.votes[pid] = target
            self.bump()
            if len(self.votes) == len(self.players):
                self._close_vote()
        elif kind == "guess":
            if self.phase != "mole_guess" or pid not in self.caught or pid in self.guesses:
                raise GameError("wrong_phase", "Only a caught Mole guesses, once")
            self.guesses[pid] = self._tile(action)
            self.bump()
            if all(m in self.guesses for m in self.caught):
                self._finish()
        else:
            raise GameError("bad_action", "Unknown action")

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "briefing":
            self._enter("hint")
        elif self.phase == "hint":
            self._close_hint_round()
        elif self.phase == "vote":
            self._close_vote()
        elif self.phase == "mole_guess":
            self._finish()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        is_player = pid in self.round_scores
        is_mole = pid in self.moles
        mine = self._pending_swap(pid) if is_mole and self.phase == "hint" else None
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": HINT_ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "mural": [dict(t) for t in self.mural],
            "moles": len(self.moles),  # how many, never who
            "you": {
                "is_mole": is_mole,
                # Only innocent players see the painting. Never a Mole, never a TV.
                "target": self.target if is_player and not is_mole else None,
                "can_swap": is_mole and self.phase == "hint" and not any(s["by"] == pid for s in self.swaps),
                "swap_with": mine["with"] if mine else None,
                "guessed": pid in self.guesses,
            },
            "hinted": sorted(self.current) if self.phase == "hint" else [],
            "your_hint": self.current.get(pid) if self.phase == "hint" else None,
            "your_hints": list(self.played.get(pid, [])),  # what you really hinted (only yours)
            "hints": [dict(h) for h in self.hints],
            # Rounds whose reveal had a swap in it: public, but not who did it.
            "swapped_rounds": sorted({s["round"] + 1 for s in self.swaps if s["done"]}),
            "votes_in": len(self.votes),
            "you_voted": self.votes.get(pid),
            "caught": list(self.caught),
        }
        if self.phase == "final" and self.result:
            view["result"] = self.result
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.result:
            return []
        out: list[dict[str, str]] = []
        for m in self.moles:
            name = self.name_of(m)
            if m not in self.caught:
                out.append(
                    {"icon": "🕶️", "title": "Undercover", "text": f"{name} was a Mole and nobody caught them"}
                )
            elif m in self.result["stole"]:
                out.append(
                    {
                        "icon": "🖌️",
                        "title": "Stolen masterpiece",
                        "text": f"{name} got caught, then named the painting",
                    }
                )
        hunters = [self.name_of(p) for p, t in self.votes.items() if t in self.caught and p not in self.moles]
        if hunters and len(self.result["stole"]) < len(self.caught):
            out.append(
                {"icon": "🔦", "title": "Mole hunters", "text": f"{', '.join(hunters)} sniffed out the Mole"}
            )
        for s in self.result["swaps"]:
            text = f"{self.name_of(s['by'])} swapped hints with {self.name_of(s['with'])}"
            out.append({"icon": "🔀", "title": "Switcheroo", "text": text})
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "moles": len(self.moles),
            "caught": bool(self.result and self.result["caught"]),
        }
