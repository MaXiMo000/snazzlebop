#!/usr/bin/env python3
"""End-to-end simulator: a host and bots play every game against a running server.

    python scripts/simulate.py --base http://localhost:10000 [--bots 5] [--seed 7]

Black-box, like real clients: HTTP to create/join, WebSockets to play, the token in the first
frame. Every frame each bot receives is kept and checked:

- per-phase key whitelists: a view may only carry the fields that phase allows (so a new field
  that leaks a secret fails here before it ships);
- planted secrets: each bot guesses a unique price; no other bot may see it before the reveal;
- Alibi: exactly one bot is told it is the killer, nobody else sees fake slots, and the final
  truth table matches every innocent's card;
- Price: the revealed modifier/nonce must hash to the commitment shown before guessing;
- session scores go up after every game.

Exit code 0 = all games completed and every check passed. Needs `httpx` and `websockets`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets

TIMEOUT = 15.0
# Errors a bot may legitimately trigger (racing for the same question, etc.). Anything else fails.
EXPECTED_ERRORS = {"already_known", "no_asks", "wrong"}  # wrong: the deliberate crossword miss

ALLOWED_KEYS = {
    ("frenemy", "rank"): {"game", "phase", "round", "rounds", "remaining", "prompt", "players", "submitted"}
    | {"you_submitted", "you_predicted"},
    ("frenemy", "reveal"): {"game", "phase", "round", "rounds", "remaining", "prompt", "players", "submitted"}
    | {"you_submitted", "you_predicted", "result"},
    ("price", "guess"): {"game", "phase", "round", "rounds", "remaining", "item", "commit", "chips", "locked"}
    | {"you_locked", "rollover", "your_guesses", "rigged", "final_round", "sabotage_left", "your_sabotage"}
    | {"your_double", "showcase", "last_duel"},
    ("price", "duel"): {"game", "phase", "round", "rounds", "remaining", "item", "commit", "chips", "locked"}
    | {
        "you_locked",
        "rollover",
        "rigged",
        "final_round",
        "sabotage_left",
        "your_sabotage",
        "your_double",
        "duel",
    },
    ("alibi", "briefing"): {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
        "setting",
        "victim",
        "scene",
    }
    | {"murder_slot", "murder_label", "slots", "locations", "you", "claims", "flags", "clues", "log"}
    | {"votes_in", "you_voted", "objections"},
}
ALLOWED_KEYS[("alibi", "interrogate")] = ALLOWED_KEYS[("alibi", "briefing")]
ALLOWED_KEYS[("alibi", "vote")] = ALLOWED_KEYS[("alibi", "briefing")]
ALLOWED_KEYS[("telepathy", "pick")] = {
    "game",
    "phase",
    "round",
    "rounds",
    "remaining",
    "players",
    "category",
    "contrarian",
    "streaks",
} | {
    "locked",
    "you_locked",
    "your_pick",
}
for _phase in ("bet", "play"):
    ALLOWED_KEYS[("blackjack", _phase)] = {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
        "chips",
        "mode",
        "active",
        "out",
        "side",
        "side_sizes",
        "chaos",
        "chaos_coming",
    } | {
        "bets",
        "bet_sizes",
        "hands",
        "dealer",
        "shoe_left",
        "reshuffled",
        "turn",
        "you",
    }
ALLOWED_KEYS[("crossword", "solve")] = {
    "game",
    "phase",
    "round",
    "rounds",
    "remaining",
    "players",
    "width",
    "mode",
    "teams",
    "team_totals",
    "letters_left",
    "letter_cost",
} | {
    "height",
    "cells",
    "clues",
    "hint_level",
    "locked_for",
}
ALLOWED_KEYS[("dice", "bid")] = {
    "game",
    "phase",
    "round",
    "rounds",
    "remaining",
    "players",
    "counts",
    "total",
} | {
    "start_dice",
    "bid",
    "turn",
    "you",
    "out",
    "history",
}
for _phase in ("briefing", "hint", "vote", "mole_guess"):
    ALLOWED_KEYS[("mural", _phase)] = {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
        "mural",
        "you",
        "moles",
        "swapped_rounds",
        "your_hints",
    } | {
        "hinted",
        "your_hint",
        "hints",
        "votes_in",
        "you_voted",
        "caught",
    }


class Check(AssertionError):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise Check(msg)


class Bot:
    def __init__(self, name: str, pid: str, token: str, ws: Any) -> None:
        self.name, self.pid, self.token, self.ws = name, pid, token, ws
        self.raw: list[str] = []
        self.state: dict[str, Any] | None = None
        self.errors: list[str] = []
        self.closed: int | None = None
        self.next_send = 0.0
        self.cond = asyncio.Condition()

    async def read(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get("t") == "state":
                    self.raw.append(raw)
                    self.state = msg
                elif msg.get("t") == "error":
                    self.errors.append(msg.get("code", "?"))
                async with self.cond:
                    self.cond.notify_all()
        except websockets.ConnectionClosed as exc:
            self.closed = exc.rcvd.code if exc.rcvd else 1006

    async def until(self, pred: Any, what: str) -> dict[str, Any]:
        async with self.cond:
            try:
                await asyncio.wait_for(
                    self.cond.wait_for(lambda: self.state is not None and pred(self.state)), TIMEOUT
                )
            except TimeoutError:
                raise Check(f"{self.name}: timed out waiting for {what} ({self.where()})") from None
        assert self.state is not None
        return self.state

    def where(self) -> str:
        g = (self.state or {}).get("game") or {}
        locked = f"locked={len(g.get('locked') or [])} " if "locked" in g else ""
        stage = f"{g.get('game')}/{g.get('phase')} r{g.get('round')}"
        return f"{stage} {locked}closed={self.closed} errors={self.errors[-5:]}"

    async def send(self, **msg: Any) -> None:
        # The server closes sockets that exceed 8 msg/s (burst 16) with 1008. Bots run at machine
        # speed, so pace them at 5/s: still far faster than a human, never a flood.
        loop = asyncio.get_running_loop()
        wait = self.next_send - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        self.next_send = max(loop.time(), self.next_send) + 0.2
        await self.ws.send(json.dumps(msg))


def game_is(game: str, phase: str, rnd: int | None = None):
    def pred(s: dict[str, Any]) -> bool:
        g = s.get("game")
        return bool(g and g["game"] == game and g["phase"] == phase and (rnd is None or g["round"] == rnd))

    return pred


async def all_until(bots: list[Bot], pred: Any, what: str) -> None:
    await asyncio.gather(*(b.until(pred, what) for b in bots))


async def skip(host: Bot) -> None:
    assert host.state is not None
    await host.send(t="skip", stage=host.state["stage"])


def totals(bot: Bot) -> dict[str, int]:
    assert bot.state is not None
    return {p["id"]: p["total"] for p in bot.state["players"]}


def values(obj: Any) -> Any:
    """Every leaf value in a decoded frame."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from values(v)
    elif not isinstance(obj, float):
        yield obj


# -- secrecy checks over every frame each bot received ----------------------------------------------
def check_frames(bots: list[Bot], game: str, start: dict[str, int], planted: dict[str, set[int]]) -> int:
    """planted: pid -> every amount that player guessed (only they may see them before a reveal)."""
    killers = set()
    moles = set()
    paintings = set()
    checked = 0
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            msg = json.loads(raw)
            g = msg.get("game")
            if not g or g["game"] != game:
                continue
            checked += 1
            allowed = ALLOWED_KEYS.get((game, g["phase"]))
            if allowed is not None:
                extra = set(g) - allowed
                check(not extra, f"{b.name} saw unexpected fields {extra} in {game}/{g['phase']}")
            if game == "price" and g["phase"] == "guess":
                seen = set(values(g))  # exact values, not substrings: "remaining" floats hold any digits
                for other, amounts in planted.items():
                    if other != b.pid:
                        leak = amounts & seen
                        where = [k for k, v in g.items() if leak & set(values(v))]
                        check(
                            not leak, f"{b.name} saw another player's guess {sorted(leak)} in {where} early"
                        )
                mine = set(g.get("your_guesses") or [])
                check(mine <= planted.get(b.pid, set()), f"{b.name} was shown guesses that aren't theirs")
                own = MOVES.get(b.pid, {})
                check(
                    g["your_sabotage"] in (None, own.get("sabotage")), f"{b.name} saw someone else's sabotage"
                )
                check(not g["your_double"] or own.get("double"), f"{b.name} saw someone else's double")
            if game == "alibi":
                you = g["you"]
                if you["is_killer"]:
                    killers.add(b.pid)
                else:
                    check(you["fake_slots"] is None, f"{b.name} (innocent) was shown fake slots")
                    check(you["plant"] is None and not you["can_plant"], f"{b.name} (innocent) saw the plant")
                if g["phase"] != "final":
                    check("result" not in g and '"truth"' not in raw, f"{b.name} saw the solution early")
            if game == "telepathy" and g["phase"] == "pick":
                check("result" not in g, f"{b.name} saw picks before the reveal")
                mine = PICKS.get((b.pid, g["round"]))
                check(g["your_pick"] in (None, mine), f"{b.name} was shown a pick that isn't theirs")
            if game == "mural" and g["phase"] != "final":
                you = g["you"]
                check("result" not in g, f"{b.name} saw the mural solution early")
                if you["is_mole"]:
                    moles.add(b.pid)
                    check(you["target"] is None, f"{b.name} is the Mole but was shown the painting")
                else:
                    check(you["target"] is not None, f"{b.name} (innocent) wasn't shown the painting")
                    paintings.add(you["target"])
                if g["phase"] == "hint":
                    check(
                        g["your_hint"] in (None, HINTS.get((b.pid, g["round"]))),
                        f"{b.name} was shown a hint that isn't theirs",
                    )
                check(you["swap_with"] in (None, SWAPS.get(b.pid)), f"{b.name} saw someone else's Switcheroo")
            if game == "blackjack" and g["phase"] in ("bet", "play"):
                check(len(g["dealer"]["cards"]) <= 1, f"{b.name} saw the dealer's hole card")
                check("shoe" not in g and "deck" not in g, f"{b.name} saw the shoe")
            if game == "crossword" and g["phase"] == "solve":
                open_clues = [c for c in g["clues"] if not c["solved_by"]]
                check(all("answer" not in c for c in open_clues), f"{b.name} saw an unsolved answer")
                solved_cells = sum(c["len"] for c in g["clues"] if c["solved_by"])
                lit = sum(1 for c in g["cells"] if c["letter"] and not c["bought"])
                check(
                    lit <= solved_cells + g["hint_level"] * len(g["clues"]), f"{b.name} saw letters too early"
                )
                if g["mode"] == "race" and b.pid != BUYER.get("pid"):
                    check(
                        not any(c["bought"] for c in g["cells"]), f"{b.name} saw a letter someone else bought"
                    )
    if game == "alibi":
        check(len(killers) == 1, f"expected exactly one bot told it is the killer, got {len(killers)}")
    if game == "mural":
        want = 2 if len(bots) >= 7 else 1
        check(len(moles) == want, f"expected {want} bots told they are a Mole, got {len(moles)}")
        check(len(paintings) == 1, "innocents were shown different paintings")
    return checked


# -- games --------------------------------------------------------------------------------------------
PICKS: dict[tuple[str, int], int] = {}  # (pid, round) -> the option that bot picked
HINTS: dict[tuple[str, int], int] = {}  # (pid, round) -> the tile that bot hinted
BUYER: dict[str, str] = {}  # the bot that buys a crossword letter (nobody else may see it)
SWAPS: dict[str, str] = {}  # mole -> who it swapped hints with (secret until the end)


async def play_blackjack(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    by_id = {b.pid: b for b in bots}
    first = {b.pid: len(b.raw) for b in bots}  # this game's frames only (the log spans the session)
    chaos_seen_at: int | None = None
    for rnd in range(1, 20):
        await all_until(
            bots,
            lambda s, rnd=rnd: (
                game_is("blackjack", "bet", rnd)(s) or (s.get("game") or {}).get("phase") == "final"
            ),
            f"blackjack bet {rnd}",
        )
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] == "final":
            break
        if g["chaos"] and chaos_seen_at is None:
            chaos_seen_at = rnd
        before = dict(g["chips"])
        live = [b for b in bots if b.pid in g["active"] and g["chips"][b.pid] >= 50]
        for i, b in enumerate(live):
            chips = g["chips"][b.pid]
            amount = 100 if chips >= 100 else 50
            side = {}
            # Every other bot backs the next player's hand when it can afford both: side bets settle
            # inside "net", so the chips-moved check below covers them too.
            if i % 2 == 1 and len(live) > 1 and chips >= amount + 50:
                side = {"side_on": live[(i + 1) % len(live)].pid, "side_amount": 50}
            await b.send(t="act", a="bet", amount=amount, **side)
        await all_until(bots, lambda s: (s.get("game") or {}).get("phase") in ("play", "settle"), "deal")
        for _ in range(60):  # one action per loop; each waits for the table to move on
            g = host.state["game"]  # type: ignore[index]
            if g["phase"] != "play":
                break
            turn = g["turn"]
            who = by_id[turn["player"]]
            hand = g["hands"][who.pid][turn["hand"]]
            stage = (turn["player"], turn["hand"], len(hand["cards"]))
            await who.send(t="act", a="hit" if hand["value"] < 13 else "stand")

            def moved(s: dict[str, Any], stage: tuple = stage) -> bool:
                gg = s.get("game") or {}
                t = gg.get("turn")
                if gg.get("phase") != "play" or t is None:
                    return True
                return (t["player"], t["hand"], len(gg["hands"][t["player"]][t["hand"]]["cards"])) != stage

            await host.until(moved, "blackjack turn")
        await all_until(bots, game_is("blackjack", "settle", rnd), f"blackjack settle {rnd}")
        g = host.state["game"]  # type: ignore[index]
        for pid, net in g["result"]["net"].items():
            check(
                g["chips"][pid] - before[pid] == net,
                f"blackjack: chips moved {g['chips'][pid] - before[pid]} != net {net}",
            )
        await skip(host)
    # The Chaos card shows only on its own hand: no frame of an earlier hand may carry it.
    for b in bots:
        for raw in b.raw[first[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") == "blackjack" and gg.get("phase") in ("bet", "play", "settle"):
                early = chaos_seen_at is None or gg["round"] < chaos_seen_at
                if early:
                    check(gg["chaos"] is None, f"{b.name} saw the Chaos card before its hand")


def crossword_oracle() -> dict[str, str]:
    """Clue -> answer from the repo's pools (seed + committed extras). A test oracle: bots stand in
    for people who know words."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.contentgen import KINDS

    return {e["clue"]: e["word"] for e in KINDS["crossword"].pool}


async def play_crossword(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    await all_until(bots, game_is("crossword", "solve"), "crossword solve")
    oracle = crossword_oracle()
    clues = host.state["game"]["clues"]  # type: ignore[index]
    if host.state["game"]["mode"] == "race":  # type: ignore[index]
        buyer = bots[-1]
        BUYER["pid"] = buyer.pid
        await buyer.send(t="act", a="buy", clue=clues[-1]["id"])
        await buyer.until(lambda s: any(c["bought"] for c in s["game"]["cells"]), "letter bought")
    # One honest mistake first: the server must answer "wrong", then lock that bot out briefly.
    await bots[1].send(t="act", a="guess", clue=clues[0]["id"], answer="Q" * clues[0]["len"])
    try:
        await bots[1].until(lambda s: "wrong" in bots[1].errors, "wrong guess rejected")
    except Check:
        check(False, "a wrong crossword guess wasn't rejected")
    solved, mine = 0, set()
    solvers = [b for b in bots if b is not bots[1]]  # bots[1] is serving its 2 s lockout
    for i, c in enumerate(clues):
        word = oracle.get(c["clue"])
        if word:  # generated clues aren't in the seed oracle: leave those to the timer
            await solvers[i % len(solvers)].send(t="act", a="guess", clue=c["id"], answer=word)
            solved += 1
            mine.add(c["id"])
    check(solved > 0, "no crossword clue was solvable from the pools")

    def settled(s: dict[str, Any]) -> bool:  # every guess sent has landed (or the timer ended it)
        g = s.get("game") or {}
        return g.get("phase") != "solve" or all(c["solved_by"] for c in g["clues"] if c["id"] in mine)

    await host.until(settled, "crossword guesses applied")
    if host.state["game"]["phase"] == "solve":  # type: ignore[index]
        await skip(host)
    await all_until(bots, game_is("crossword", "final"), "crossword final")
    g = host.state["game"]  # type: ignore[index]
    check(all("answer" in c for c in g["clues"]), "crossword answers weren't revealed at the end")


async def play_dice(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots bid a little higher or call liar. Every reveal must show exactly the dice each bot was shown
    while bidding (nobody's dice change behind their back), and nobody sees others' dice before it."""
    by_id = {b.pid: b for b in bots}
    for _ in range(400):
        await host.until(lambda s: (s.get("game") or {}).get("phase") in ("bid", "reveal", "final"), "dice")
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] == "final":
            break
        if g["phase"] == "reveal":
            rnd = g["round"]
            for pid, shown in g["last"]["dice"].items():
                own = [
                    json.loads(raw)["game"]["you"]["dice"]
                    for raw in by_id[pid].raw
                    if (json.loads(raw).get("game") or {}).get("game") == "dice"
                    and json.loads(raw)["game"]["phase"] == "bid"
                    and json.loads(raw)["game"]["round"] == rnd
                ]
                check(own and own[-1] == shown, f"dice: {pid}'s revealed dice aren't the ones it was shown")
            await skip(host)
            await host.until(
                lambda s, rnd=rnd: (s["game"] or {}).get("round") != rnd or s["game"]["phase"] == "final",
                "next roll",
            )
            continue
        who = by_id[g["turn"]]
        await who.until(lambda s, t=g["turn"]: (s.get("game") or {}).get("turn") == t, "dice turn")
        bid = g["bid"]
        if bid is None or rng.random() < 0.65:
            qty, face = (
                (bid["qty"], bid["face"] + 1)
                if bid and bid["face"] < 6
                else ((bid["qty"] + 1) if bid else 1, 2)
            )
            if qty > g["total"]:
                await who.send(t="act", a="liar")
            else:
                await who.send(t="act", a="bid", qty=qty, face=face)
        else:
            await who.send(t="act", a="liar" if rng.random() < 0.85 else "spot")
        await host.until(lambda s, v=g: s["game"] != v, "dice move")
    g = host.state["game"]  # type: ignore[index]
    check(g["phase"] == "final", "liar's dice never finished")
    check(sorted(g["standings"]) == sorted(b.pid for b in bots), "dice standings miss a player")
    n = len(g["standings"])
    print(f"  dice: {n} players, {len(g['history'])} challenges")


async def play_telepathy(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    PICKS.clear()
    n = len(bots)
    streak = {b.pid: 0 for b in bots}
    for rnd in range(1, 7):
        await all_until(bots, game_is("telepathy", "pick", rnd), f"telepathy pick {rnd}")
        for i, b in enumerate(bots):
            opt = (i + rnd) % 3  # small clusters, sometimes a majority
            PICKS[(b.pid, rnd)] = opt
            await b.send(t="act", a="pick", option=opt)
        await all_until(bots, game_is("telepathy", "reveal", rnd), f"telepathy reveal {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        check(
            r["picks"] == {b.pid: PICKS[(b.pid, rnd)] for b in bots},
            "revealed picks don't match what was sent",
        )
        counts = {o: list(r["picks"].values()).count(o) for o in set(r["picks"].values())}
        for pid, opt in r["picks"].items():
            if r["contrarian"]:  # no tax; only a pick nobody else made scores
                base = 200 if counts[opt] == 1 else 0
            else:
                base = 0 if counts[opt] > n / 2 else 100 * (counts[opt] - 1)
            streak[pid] = streak[pid] + 1 if base > 0 else 0
            want = base + (50 * min(streak[pid] - 1, 3) if streak[pid] >= 2 else 0)
            check(r["points"][pid] == want, f"telepathy scoring is off for option {opt}")
        check(r["streaks"] == streak, "telepathy streaks don't follow the rules")
        await skip(host)


async def play_mural(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    HINTS.clear()
    SWAPS.clear()
    await all_until(bots, game_is("mural", "briefing"), "mural briefing")
    moles = [b for b in bots if b.state["game"]["you"]["is_mole"]]  # type: ignore[index]
    mole = moles[0]
    target = next(b for b in bots if b not in moles).state["game"]["you"]["target"]  # type: ignore[index]
    tiles = host.state["game"]["mural"]  # type: ignore[index]

    def related(i: int) -> bool:
        a, t = tiles[i], tiles[target]
        return i != target and (a["color"] == t["color"] or a["kind"] == t["kind"])

    await skip(host)
    victim = next(b for b in bots if b not in moles)
    for rnd in (1, 2):
        await all_until(bots, game_is("mural", "hint", rnd), f"mural hint {rnd}")
        if rnd == 1:  # the first Mole pulls a Switcheroo on an innocent
            SWAPS[mole.pid] = victim.pid
            await mole.send(t="act", a="swap", target=victim.pid)
            await mole.until(lambda s: s["game"]["you"]["swap_with"] is not None, "swap applied")
        for b in bots:
            used = {HINTS.get((b.pid, r)) for r in (1, 2)}
            choices = [i for i in range(16) if i not in used and (b in moles or related(i))]
            tile = rng.choice(choices)
            HINTS[(b.pid, rnd)] = tile
            await b.send(t="act", a="hint", tile=tile)
    await all_until(bots, game_is("mural", "vote"), "mural vote")
    shown = host.state["game"]["hints"][0]  # type: ignore[index]
    check(
        (shown[mole.pid], shown[victim.pid]) == (HINTS[(victim.pid, 1)], HINTS[(mole.pid, 1)]),
        "the Switcheroo didn't swap the two hints in the reveal",
    )
    check(host.state["game"]["swapped_rounds"] == [1], "the swap wasn't announced")  # type: ignore[index]
    for b in bots:
        # Innocents vote for whoever dropped the most unrelated hints; the Mole deflects.
        others = [o for o in bots if o is not b]
        if b in moles:
            pick = rng.choice(others)
        else:
            pick = max(
                others, key=lambda o: (sum(not related(HINTS[(o.pid, r)]) for r in (1, 2)), rng.random())
            )
        await b.send(t="act", a="vote", target=pick.pid)
    await all_until(
        bots, lambda s: (s.get("game") or {}).get("phase") in ("mole_guess", "final"), "mural vote close"
    )
    if host.state["game"]["phase"] == "mole_guess":  # type: ignore[index]
        for m in moles:
            if m.pid in host.state["game"]["caught"]:  # type: ignore[index]
                await m.send(t="act", a="guess", tile=rng.randrange(16))
    await all_until(bots, game_is("mural", "final"), "mural final")
    r = host.state["game"]["result"]  # type: ignore[index]
    check(
        sorted(r["moles"]) == sorted(m.pid for m in moles) and r["target"] == target,
        "mural result doesn't match what the bots were told",
    )
    check(
        r["swaps"] == [{"round": 0, "by": mole.pid, "with": victim.pid, "done": True}],
        "swap missing from the result",
    )
    outcome = "stole the win" if r["stole"] else "caught" if r["caught"] else "escaped"
    print(f"  mural: {len(moles)} mole(s), {outcome}")


async def play_frenemy(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    ids = [b.pid for b in bots]
    for rnd in (1, 2, 3):
        await all_until(bots, game_is("frenemy", "rank", rnd), f"frenemy rank {rnd}")
        guesses = {b.pid: rng.randint(1, len(ids)) for b in bots}  # mirror check: secret until the reveal
        for b in bots:
            order = ids[:]
            rng.shuffle(order)
            await b.send(t="act", a="rank", order=order, predict=guesses[b.pid])
            await b.until(
                lambda s, b=b: (
                    (s.get("game") or {}).get("you_predicted") is not None
                    or (s.get("game") or {}).get("phase") != "rank"
                ),
                "rank applied",
            )
        for b in bots:
            for raw in b.raw:
                g = json.loads(raw).get("game") or {}
                if g.get("game") == "frenemy" and g.get("phase") == "rank" and g.get("round") == rnd:
                    check(
                        g.get("you_predicted") in (None, guesses[b.pid]),
                        f"{b.name} saw someone else's mirror guess",
                    )
        await all_until(bots, game_is("frenemy", "reveal", rnd), f"frenemy reveal {rnd}")
        for b in bots:
            res = b.state["game"]["result"]  # type: ignore[index]
            check(set(res) == set(ids) and all(r["played"] for r in res.values()), "reveal missing players")
            for pid, r in res.items():
                miss = abs(guesses[pid] - r["others_avg"])
                want = 50 if miss <= 0.5 else 25 if miss <= 1.5 else 0
                check(
                    r["predicted"] == guesses[pid] and r["mirror"] == want,
                    f"frenemy: wrong mirror bonus for {pid}",
                )
        await skip(host)


async def play_alibi(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    await all_until(bots, game_is("alibi", "briefing"), "alibi briefing")
    killer = next(b for b in bots if b.state["game"]["you"]["is_killer"])  # type: ignore[index]
    cards = {b.pid: b.state["game"]["you"]["card"] for b in bots}  # type: ignore[index]
    killer_fakes = set(killer.state["game"]["you"]["fake_slots"])  # type: ignore[index]
    murder_slot = killer.state["game"]["murder_slot"]  # type: ignore[index]
    await skip(host)
    innocents = [b for b in bots if b is not killer]
    for rnd in (1, 2, 3):
        await all_until(bots, game_is("alibi", "interrogate", rnd), f"alibi round {rnd}")
        if rnd == 1:  # the killer frames someone; it must stay invisible until the next clue drop
            n_clues = len(host.state["game"]["clues"])  # type: ignore[index]
            await killer.send(t="act", a="plant", target=innocents[0].pid, slot=rng.randrange(6))
            await killer.until(lambda s: s["game"]["you"]["plant"] is not None, "plant applied")
            check(len(host.state["game"]["clues"]) == n_clues, "a planted clue showed up early")  # type: ignore[index]
        if rnd == 2:  # an innocent objects to the killer's lie: the server must sustain it
            fake = next(sl for sl in sorted(set(range(6))) if sl in killer_fakes and sl != murder_slot)
            await innocents[1].send(t="act", a="object", target=killer.pid, slot=fake)
            await innocents[1].until(lambda s: bool(s["game"]["objections"]), "objection applied")
            check(
                innocents[1].state["game"]["objections"][0]["sustained"], "objection to a lie was overruled"
            )  # type: ignore[index]
        # Each act waits until the server applied (or refused) it before the next, and the host only
        # skips after all of them: over a real network a fixed sleep let the skip overtake the last
        # bot's ask ("wrong_phase").
        for b in bots:
            slot = rng.randrange(6)
            errors = len(b.errors)
            await b.send(t="act", a="reveal", slot=slot)

            def revealed(s: dict[str, Any], b: Bot = b, slot: int = slot, errors: int = errors) -> bool:
                mine = any(c["speaker"] == b.pid and c["slot"] == slot for c in s["game"]["claims"])
                return mine or len(b.errors) > errors

            await b.until(revealed, "alibi reveal applied")
            errors, asks = len(b.errors), b.state["game"]["you"]["asks_left"]  # type: ignore[index]
            target = rng.choice([o for o in bots if o is not b])
            await b.send(t="act", a="ask", target=target.pid, slot=rng.randrange(6))

            def asked(s: dict[str, Any], b: Bot = b, asks: int = asks, errors: int = errors) -> bool:
                return s["game"]["you"]["asks_left"] < asks or len(b.errors) > errors

            await b.until(asked, "alibi ask applied")
        await skip(host)
    await all_until(bots, game_is("alibi", "vote"), "alibi vote")
    flagged: dict[str, int] = {}
    for f in host.state["game"]["flags"]:  # type: ignore[index]
        for p in f["players"]:
            flagged[p] = flagged.get(p, 0) + 1
    for b in bots:
        options = [o.pid for o in bots if o is not b]
        target = max(options, key=lambda p: (flagged.get(p, 0), rng.random()))
        await b.send(t="act", a="vote", target=target)
    await all_until(bots, game_is("alibi", "final"), "alibi final")
    result = host.state["game"]["result"]  # type: ignore[index]
    check(result["killer"] == killer.pid, "final killer differs from the one the killer bot was told")
    for b in bots:
        for entry in cards[b.pid]:
            truthful = result["truth"][b.pid][entry["slot"]] == entry["location"]
            hazy = result["hazy"] or {}
            lie = (b is killer and entry["slot"] in result["fake_slots"]) or (
                hazy.get("player") == b.pid and hazy.get("slot") == entry["slot"]  # an honest mistake
            )
            check(
                truthful != lie, f"{b.name}'s card disagrees with the revealed truth at slot {entry['slot']}"
            )
    print(f"  alibi: killer {'caught' if result['caught'] else 'escaped'}; flags: {sum(flagged.values())}")


# Secret Price moves each bot made: only its owner may ever see them before the reveal.
MOVES: dict[str, dict[str, Any]] = {}


async def play_price(host: Bot, bots: list[Bot], planted: dict[str, set[int]], rng: random.Random) -> None:
    MOVES.clear()
    for rnd in range(1, 6):
        await all_until(bots, game_is("price", "guess", rnd), f"price guess {rnd}")
        commit = host.state["game"]["commit"]  # type: ignore[index]
        if rnd == 1:  # bot 1 plants a sabotage on the host (who guesses low and usually wins)
            MOVES[bots[1].pid] = {"sabotage": host.pid}
            await bots[1].send(t="act", a="sabotage", target=host.pid)
        if rnd == 5:  # final item: host and bot 2 go Double or Nothing
            for b in (bots[0], bots[2]):
                MOVES.setdefault(b.pid, {})["double"] = True
                await b.send(t="act", a="double", on=True)
        for i, b in enumerate(bots):
            # Distinct per bot and round. Even bots stay under the cheapest possible price ($240 item
            # x0.5 = $120) so every round has a winner; odd bots overshoot the priciest ($2.6M x2).
            amount = 3 + rnd * 20 + i if i % 2 == 0 else 9_000_000 + rnd * 1_000 + i
            # Host hedges twice. Every planted guess must be unique across bots and odd (every price is
            # even), so a match in someone else's frame can only be a real leak: +10,000 keeps it odd and
            # clear of every other bot's guesses (small ones under 200, big ones over 9,000,000).
            extra = {"amount2": amount + 10_000} if i == 0 and rnd <= 2 else {}
            planted.setdefault(b.pid, set()).update([amount, *extra.values()])
            await b.send(t="act", a="guess", amount=amount, **extra)
        await all_until(bots, game_is("price", "reveal", rnd), f"price reveal {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        check(r["commit"] == commit, "commitment changed between guess and reveal")
        proof = hashlib.sha256(f"{r['modifier']}:{r['nonce']}".encode()).hexdigest()
        check(proof == commit, "revealed modifier/nonce do not match the sealed commitment")
        check(r["true_price"] == round(r["base_price"] * r["modifier"]), "true price != base * modifier")
        if rnd == 1:
            check(r["sabotage"] == {bots[1].pid: host.pid}, "sabotage missing from the reveal")
        if rnd == 5:
            check(set(r["double"]) == {bots[0].pid, bots[2].pid}, "double-or-nothing missing from the reveal")
            check(len(host.state["game"].get("showcase", [])) == 3, "the last item isn't a 3-prize showcase")  # type: ignore[index]
            check(
                r["base_price"] == sum(host.state["game"]["showcase_prices"]),
                "showcase total != sum of prizes",
            )  # type: ignore[index]
        await skip(host)
        if rnd < 5:  # the price duel between items: picks are secret until it resolves
            await all_until(bots, game_is("price", "duel", rnd), f"price duel {rnd}")
            picks = {b.pid: rng.randrange(2) for b in bots}
            for b in bots:
                await b.send(t="act", a="duel", pick=picks[b.pid])
            await all_until(bots, game_is("price", "guess", rnd + 1), f"price guess {rnd + 1}")
            for b in bots:
                for raw in b.raw:
                    g = json.loads(raw).get("game") or {}
                    if g.get("game") == "price" and g.get("phase") == "duel" and g.get("round") == rnd:
                        check(
                            g["duel"]["your_pick"] in (None, picks[b.pid]), f"{b.name} saw another duel pick"
                        )
                        check('"price"' not in json.dumps(g["duel"]), f"{b.name} saw duel prices early")
            d = host.state["game"]["last_duel"]  # type: ignore[index]
            a, z = (x["price"] for x in d["items"])
            answer = 0 if a > z else 1 if z > a else None
            want = sorted(pid for pid, pk in picks.items() if answer is None or pk == answer)
            check(d["right"] == want and d["picks"] == picks, "price duel scored the wrong players")


def price_points(
    history: list[dict[str, Any]], ids: list[str], duels: list[dict[str, Any]]
) -> dict[str, int]:
    """Recompute Price Is Weird scoring from what was revealed, in order: each item's pot and sabotage
    steals (doubles/wipes on the Showcase), then the price duel that followed it (+25 per right pick)."""
    pts = dict.fromkeys(ids, 0)
    for i, r in enumerate(history):
        if i > 0 and i - 1 < len(duels):
            for pid in duels[i - 1]["right"]:
                pts[pid] += 25
        w = r["winner"]
        if w:
            pts[w] += r["pot"]
            thieves = [s for s, t in r["sabotage"].items() if t == w]
            if thieves:
                share = (r["pot"] // 2) // len(thieves)
                pts[w] -= share * len(thieves)
                for s in thieves:
                    pts[s] += share
        for pid, outcome in r["double"].items():
            pts[pid] = pts[pid] * 2 if outcome == "doubled" else 0
    return pts


# -- driver -------------------------------------------------------------------------------------------
async def run(base: str, n_bots: int, seed: int, only: list[str] | None = None) -> None:
    rng = random.Random(seed)
    origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    ws_base = origin.replace("http", "ws", 1)
    async with httpx.AsyncClient(base_url=base, headers={"Origin": origin}, timeout=10) as http:
        r = await http.post("/api/rooms", json={"name": "Host"})
        check(r.status_code == 201, f"create room: {r.status_code} {r.text}")
        room = r.json()
        code = room["code"]
        seats = [("Host", room["player_id"], room["token"])]
        for i in range(n_bots):
            r = await http.post(f"/api/rooms/{code}/join", json={"name": f"Bot {i + 1}"})
            check(r.status_code == 200, f"join: {r.status_code} {r.text}")
            seats.append((f"Bot {i + 1}", r.json()["player_id"], r.json()["token"]))

    bots: list[Bot] = []
    readers = []
    for name, pid, token in seats:
        ws = await websockets.connect(f"{ws_base}/ws/{code}", origin=origin, max_size=2**16)
        await ws.send(json.dumps({"t": "auth", "token": token}))
        bot = Bot(name, pid, token, ws)
        bots.append(bot)
        readers.append(asyncio.create_task(bot.read()))
    host = bots[0]
    try:
        await all_until(
            bots, lambda s: sum(p["connected"] for p in s["players"]) == len(bots), "everyone online"
        )
        games = ["frenemy", "alibi", "price", "telepathy", "mural", "blackjack", "crossword", "dice"]
        if len(bots) >= 3:
            games.insert(6, "blackjack-tournament")
        if len(bots) >= 4:
            games.append("crossword-teams")
        for name in games:
            if only and name not in only and name.split("-")[0] not in only:
                continue
            game = name.split("-")[0]
            before = totals(host)
            start = {b.pid: len(b.raw) for b in bots}
            planted: dict[str, set[int]] = {}
            if name == "blackjack-tournament":
                await host.send(t="start", game=game, options={"mode": "tournament"})
            elif name == "crossword-teams":
                await host.send(t="start", game=game, options={"mode": "teams"})
            else:
                await host.send(t="start", game=game)
            if game == "frenemy":
                await play_frenemy(host, bots, rng)
            elif game == "alibi":
                await play_alibi(host, bots, rng)
            elif game == "price":
                await play_price(host, bots, planted, rng)
            elif game == "telepathy":
                await play_telepathy(host, bots, rng)
            elif game == "blackjack":
                await play_blackjack(host, bots, rng)
            elif game == "crossword":
                await play_crossword(host, bots, rng)
            elif game == "dice":
                await play_dice(host, bots, rng)
            else:
                await play_mural(host, bots, rng)
            await all_until(bots, lambda s: s["room"]["phase"] == "results", f"{game} results")
            after = totals(host)
            if game == "price":
                # Double or Nothing can wipe scores, so "went up" isn't a rule here. Instead every
                # player's points must be exactly what the revealed history says they earned.
                g = host.state["game"]  # type: ignore[index]
                want = price_points(g["history"], [b.pid for b in bots], g["duels"])
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"price: scoreboard {got} != points from the revealed history {want}")
            elif name == "blackjack-tournament":
                # Placement points: 100 per player outlasted, +300 for a sole survivor.
                g = host.state["game"]  # type: ignore[index]
                order, n = g["standings"], len(g["standings"])
                sole = len(g["active"]) == 1
                want = {
                    pid: 100 * (n - 1 - i) + (300 if i == 0 and sole else 0) for i, pid in enumerate(order)
                }
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"blackjack tournament: scores {got} != placings {want}")
                check(sorted(order) == sorted(b.pid for b in bots), "tournament standings miss a player")
            elif game == "blackjack":
                # The house has an edge, so a table can lose overall: each score must be net chips.
                chips = host.state["game"]["chips"]  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == {pid: chips[pid] - 1000 for pid in got}, f"blackjack: scores {got} != net chips")
            else:
                check(sum(after.values()) > sum(before.values()), f"{game}: session scores did not go up")
            frames = check_frames(bots, game, start, planted)
            for b in bots:
                bad = [e for e in b.errors if e not in EXPECTED_ERRORS]
                check(not bad, f"{b.name} got unexpected errors: {bad}")
            gained = sum(after.values()) - sum(before.values())
            hidden = sum(len(v) for v in planted.values())
            note = f", {hidden} planted guesses never leaked" if hidden else ""
            print(f"OK {name}: {frames} frames checked, {gained:+} points{note}")
            await host.send(t="lobby")
            await all_until(bots, lambda s: s["room"]["phase"] == "lobby", "lobby")
    except Check:
        for b in bots:  # who was stuck where: the first thing you want when a run fails
            print(f"  {b.name}: {b.where()}")
        raise
    finally:
        for b in bots:
            await b.ws.close()
        await asyncio.gather(*readers, return_exceptions=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:10000")
    ap.add_argument("--bots", type=int, default=5, help="players besides the host (3-7)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", nargs="+", help="play just these games (e.g. dice blackjack-tournament)")
    args = ap.parse_args()
    if not 3 <= args.bots <= 7:
        ap.error("--bots must be 3-7 (Alibi needs 4 players, rooms hold 8)")
    try:
        asyncio.run(run(args.base, args.bots, args.seed, args.only))
    except Check as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("ALL GAMES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
