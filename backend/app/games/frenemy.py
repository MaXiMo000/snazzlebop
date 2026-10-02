"""Frenemy Radar: rank everyone, then see how your self-image clashes with the group's."""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError
from .content import FRENEMY_PROMPTS

PROMPTS = FRENEMY_PROMPTS


class FrenemyRadar(Game):
    game_id: ClassVar[str] = "frenemy"
    title: ClassVar[str] = "Frenemy Radar"
    blurb: ClassVar[str] = (
        "Secretly rank everyone on silly traits (yourself too). "
        "Then see where your self-image clashes with the room."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8

    ROUNDS = 3

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"rank": 60.0, "reveal": 20.0}

    def start(self) -> None:
        self.prompts = [PROMPTS[i] for i in self.deal("prompts", len(PROMPTS), self.ROUNDS, kind="frenemy")]
        self.round = 0
        # rankings[round][ranker_id] = ordered list of player ids, index 0 = "most"
        self.rankings: list[dict[str, list[str]]] = [{} for _ in range(self.ROUNDS)]
        self.results: list[dict[str, dict[str, float]]] = []
        self.final: dict[str, Any] | None = None
        self._enter_rank()

    # -- phases -------------------------------------------------------------
    def _enter_rank(self) -> None:
        self.phase = "rank"
        self.set_deadline(self.timings["rank"])
        self.bump()

    def _enter_reveal(self) -> None:
        result = self._score_round(self.round)
        self.results.append(result)
        for pid, row in result.items():
            if row["played"]:
                self.add_points(pid, int(round(100 - row["blind_pct"])))
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _enter_next(self) -> None:
        if self.round + 1 >= self.ROUNDS:
            self.final = self._score_final()
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._enter_rank()

    # -- scoring ------------------------------------------------------------
    def _score_round(self, r: int) -> dict[str, dict[str, float]]:
        n = len(self.players)
        out: dict[str, dict[str, float]] = {}
        for p in self.players:
            own = self.rankings[r].get(p.id)
            self_rank = (own.index(p.id) + 1) if own else None
            others = [order.index(p.id) + 1 for ranker, order in self.rankings[r].items() if ranker != p.id]
            others_avg = sum(others) / len(others) if others else None
            if self_rank is None or others_avg is None:
                # Didn't play (or nobody else did): no signal, neutral score.
                out[p.id] = {
                    "self_rank": float(self_rank or 0),
                    "others_avg": float(others_avg or 0),
                    "gap": 0.0,
                    "blind_pct": 50.0,
                    "played": 0.0,
                }
                continue
            gap = others_avg - self_rank  # >0: you rate yourself higher than they do
            out[p.id] = {
                "self_rank": float(self_rank),
                "others_avg": round(others_avg, 2),
                "gap": round(gap, 2),
                "blind_pct": round(abs(gap) / (n - 1) * 100, 1),
                "played": 1.0,
            }
        return out

    def _score_final(self) -> dict[str, Any]:
        per_player: dict[str, dict[str, float]] = {}
        for p in self.players:
            rows = [res[p.id] for res in self.results if res[p.id]["played"]]
            if not rows:
                continue  # never ranked: no score, no awards
            blind = sum(r["blind_pct"] for r in rows) / len(rows)
            gap = sum(r["gap"] for r in rows) / len(rows)
            per_player[p.id] = {"blind_spot": round(blind, 1), "avg_gap": round(gap, 2)}
        awards: list[dict[str, str]] = []
        played = list(per_player)
        if played:
            optimist = max(played, key=lambda i: per_player[i]["avg_gap"])
            loved = min(played, key=lambda i: per_player[i]["avg_gap"])
            unknown = max(played, key=lambda i: per_player[i]["blind_spot"])
            clear = min(played, key=lambda i: per_player[i]["blind_spot"])
            if per_player[optimist]["avg_gap"] > 0:
                awards.append({"award": "Delusional Optimist", "player": optimist})
            if per_player[loved]["avg_gap"] < 0:
                awards.append({"award": "Secretly Loved", "player": loved})
            # Only a real blind spot earns "Unknown to Self" (never the same person as "Crystal Clear").
            if per_player[unknown]["blind_spot"] > per_player[clear]["blind_spot"]:
                awards.append({"award": "Unknown to Self", "player": unknown})
            awards.append({"award": "Crystal Clear", "player": clear})
        return {"per_player": per_player, "awards": awards}

    # -- actions ------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "rank":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "rank":
            raise GameError("wrong_phase", "Ranking is closed")
        order = action.get("order")
        ids = self.player_ids
        if (
            not isinstance(order, list)
            or len(order) != len(ids)
            or not all(isinstance(x, str) for x in order)
            or sorted(order) != sorted(ids)
        ):
            raise GameError("bad_input", "Rank every player exactly once")
        self.rankings[self.round][pid] = list(order)
        self.bump()
        if len(self.rankings[self.round]) == len(ids):
            self._enter_reveal()

    def tick(self) -> None:
        if self.finished or not self.expired():
            return
        if self.phase == "rank":
            self._enter_reveal()
        elif self.phase == "reveal":
            self._enter_next()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "rank":
            self._enter_reveal()
        elif self.phase == "reveal":
            self._enter_next()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        submitted = [p.id for p in self.players if p.id in self.rankings[self.round]]
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.ROUNDS,
            "prompt": self.prompts[self.round],
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "submitted": submitted if self.phase == "rank" else [],
            "you_submitted": pid in submitted,
        }
        if self.phase == "reveal":
            view["result"] = self.results[-1]
        if self.phase == "final" and self.final is not None:
            view["final"] = self.final
            view["history"] = [
                {"prompt": self.prompts[i], "result": res} for i, res in enumerate(self.results)
            ]
        return view

    def summary(self) -> dict[str, Any]:
        avg = None
        if self.final:
            vals = [v["blind_spot"] for v in self.final["per_player"].values()]
            avg = round(sum(vals) / len(vals), 1) if vals else None
        return {"players": len(self.players), "avg_blind_spot": avg}
