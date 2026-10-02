#!/usr/bin/env python3
"""Alibi balance harness: plays thousands of games against the pure engine and reports how often
the killer escapes. Target: 35-45% with 5 players (a good killer should win often, not always).

    python scripts/tune_alibi.py [--games 4000] [--players 4 5 6 8]

The bots are deliberately simple but not dumb: they reproduce how a table of humans plays.
- Innocents volunteer slots they haven't shared, grill whoever is involved in contradictions
  (else someone at random), and vote for the player most implicated by flags and camera clues.
- The killer volunteers only true slots, asks questions like everyone else, and votes to deflect:
  for the most implicated innocent.
- Humans aren't perfect: each innocent votes at random with probability NOISE.
"""

from __future__ import annotations

import argparse
import contextlib
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.games.alibi import Alibi  # noqa: E402
from app.games.base import GameError, Player  # noqa: E402

NOISE = 0.25  # share of innocent votes cast on a hunch


def suspicion(view: dict, me: str) -> Counter[str]:
    score: Counter[str] = Counter()
    for f in view["flags"]:
        for p in f["players"]:
            score[p] += 2 if f["kind"] == "camera" else 1
        if f["kind"] == "headcount" and not f["players"]:
            # "Someone who was there is hiding it": everyone claiming elsewhere at that time is a suspect.
            clue = next(c for c in view["clues"] if c["slot"] == f["slot"] and c["kind"] == "headcount")
            for c in view["claims"]:
                if c["slot"] == f["slot"] and c["location"] != clue["location"]:
                    score[c["speaker"]] += 1
    score.pop(me, None)
    return score


def play(n: int, rng: random.Random) -> bool:
    """One game; returns True if the killer escaped."""
    players = [Player(f"p{i}", f"P{i}") for i in range(n)]
    g = Alibi(players, rng=random.Random(rng.random()))
    g.start()
    ids = [p.id for p in players]
    g.advance()  # briefing -> interrogation
    while g.phase == "interrogate":
        for pid in rng.sample(ids, len(ids)):
            view = g.view_for(pid)
            fake = set(view["you"]["fake_slots"] or [])
            unshared = [c["slot"] for c in view["you"]["card"] if not c["shared"] and c["slot"] not in fake]
            if unshared:
                g.handle(pid, {"a": "reveal", "slot": rng.choice(unshared)})
            for _ in range(view["you"]["asks_left"]):
                sus = suspicion(g.view_for(pid), pid)
                others = [o for o in ids if o != pid]
                target = sus.most_common(1)[0][0] if sus and rng.random() < 0.7 else rng.choice(others)
                known = {(c["speaker"], c["slot"]) for c in g.view_for(pid)["claims"]}
                slots = [s for s in range(len(g.slots)) if (target, s) not in known]
                if not slots:
                    continue
                with contextlib.suppress(GameError):  # e.g. someone else just asked the same
                    g.handle(pid, {"a": "ask", "target": target, "slot": rng.choice(slots)})
        g.advance()
    for pid in ids:
        others = [o for o in ids if o != pid]
        sus = suspicion(g.view_for(pid), pid)
        if pid != g.killer and rng.random() < NOISE or not sus:
            vote = rng.choice(others)
        else:
            ranked = [p for p, _ in sus.most_common() if p != pid]
            vote = ranked[0] if pid != g.killer else next((p for p in ranked if p != pid), rng.choice(others))
        g.handle(pid, {"a": "vote", "target": vote})
    return not g.result["caught"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4000)
    ap.add_argument("--players", type=int, nargs="+", default=[4, 5, 6, 8])
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    for n in args.players:
        wins = sum(play(n, rng) for _ in range(args.games))
        rate = wins / args.games
        flag = "" if n != 5 else ("  <- in target" if 0.35 <= rate <= 0.45 else "  <- OUT OF TARGET 35-45%")
        print(f"{n} players: killer escapes {rate:6.1%} of {args.games} games{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
