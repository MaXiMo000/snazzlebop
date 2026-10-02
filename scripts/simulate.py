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
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets

TIMEOUT = 15.0
# Errors a bot may legitimately trigger (racing for the same question, etc.). Anything else fails.
EXPECTED_ERRORS = {"already_known", "no_asks"}

ALLOWED_KEYS = {
    ("frenemy", "rank"): {"game", "phase", "round", "rounds", "remaining", "prompt", "players", "submitted"}
    | {"you_submitted"},
    ("frenemy", "reveal"): {"game", "phase", "round", "rounds", "remaining", "prompt", "players", "submitted"}
    | {"you_submitted", "result"},
    ("price", "guess"): {"game", "phase", "round", "rounds", "remaining", "item", "commit", "chips", "locked"}
    | {"you_locked", "rollover", "your_guesses"},
    ("alibi", "briefing"): {"game", "phase", "round", "rounds", "remaining", "players", "victim", "scene"}
    | {"murder_slot", "murder_label", "slots", "locations", "you", "claims", "flags", "clues", "log"}
    | {"votes_in", "you_voted"},
}
ALLOWED_KEYS[("alibi", "interrogate")] = ALLOWED_KEYS[("alibi", "briefing")]
ALLOWED_KEYS[("alibi", "vote")] = ALLOWED_KEYS[("alibi", "briefing")]


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
                        check(not (amounts & seen), f"{b.name} saw another player's guess before the reveal")
                mine = set(g.get("your_guesses") or [])
                check(mine <= planted.get(b.pid, set()), f"{b.name} was shown guesses that aren't theirs")
            if game == "alibi":
                you = g["you"]
                if you["is_killer"]:
                    killers.add(b.pid)
                else:
                    check(you["fake_slots"] is None, f"{b.name} (innocent) was shown fake slots")
                if g["phase"] != "final":
                    check("result" not in g and '"truth"' not in raw, f"{b.name} saw the solution early")
    if game == "alibi":
        check(len(killers) == 1, f"expected exactly one bot told it is the killer, got {len(killers)}")
    return checked


# -- games --------------------------------------------------------------------------------------------
async def play_frenemy(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    ids = [b.pid for b in bots]
    for rnd in (1, 2, 3):
        await all_until(bots, game_is("frenemy", "rank", rnd), f"frenemy rank {rnd}")
        for b in bots:
            order = ids[:]
            rng.shuffle(order)
            await b.send(t="act", a="rank", order=order)
        await all_until(bots, game_is("frenemy", "reveal", rnd), f"frenemy reveal {rnd}")
        for b in bots:
            res = b.state["game"]["result"]  # type: ignore[index]
            check(set(res) == set(ids) and all(r["played"] for r in res.values()), "reveal missing players")
        await skip(host)


async def play_alibi(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    await all_until(bots, game_is("alibi", "briefing"), "alibi briefing")
    killer = next(b for b in bots if b.state["game"]["you"]["is_killer"])  # type: ignore[index]
    cards = {b.pid: b.state["game"]["you"]["card"] for b in bots}  # type: ignore[index]
    await skip(host)
    for rnd in (1, 2, 3):
        await all_until(bots, game_is("alibi", "interrogate", rnd), f"alibi round {rnd}")
        for b in bots:
            await b.send(t="act", a="reveal", slot=rng.randrange(6))
            target = rng.choice([o for o in bots if o is not b])
            await b.send(t="act", a="ask", target=target.pid, slot=rng.randrange(6))
        await asyncio.sleep(0.2)
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
            lie = b is killer and entry["slot"] in result["fake_slots"]
            check(
                truthful != lie, f"{b.name}'s card disagrees with the revealed truth at slot {entry['slot']}"
            )
    print(f"  alibi: killer {'caught' if result['caught'] else 'escaped'}; flags: {sum(flagged.values())}")


async def play_price(host: Bot, bots: list[Bot], planted: dict[str, set[int]]) -> None:
    for rnd in range(1, 6):
        await all_until(bots, game_is("price", "guess", rnd), f"price guess {rnd}")
        commit = host.state["game"]["commit"]  # type: ignore[index]
        for i, b in enumerate(bots):
            # Distinct per bot and round. Even bots stay under the cheapest possible price ($240 item
            # x0.5 = $120) so every round has a winner; odd bots overshoot the priciest ($2.6M x2).
            amount = 3 + rnd * 20 + i if i % 2 == 0 else 9_000_000 + rnd * 1_000 + i
            extra = {"amount2": amount + 5} if i == 0 and rnd <= 2 else {}  # host hedges twice
            planted.setdefault(b.pid, set()).update([amount, *extra.values()])
            await b.send(t="act", a="guess", amount=amount, **extra)
        await all_until(bots, game_is("price", "reveal", rnd), f"price reveal {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        check(r["commit"] == commit, "commitment changed between guess and reveal")
        proof = hashlib.sha256(f"{r['modifier']}:{r['nonce']}".encode()).hexdigest()
        check(proof == commit, "revealed modifier/nonce do not match the sealed commitment")
        check(r["true_price"] == round(r["base_price"] * r["modifier"]), "true price != base * modifier")
        await skip(host)


# -- driver -------------------------------------------------------------------------------------------
async def run(base: str, n_bots: int, seed: int) -> None:
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
        for game in ("frenemy", "alibi", "price"):
            before = totals(host)
            start = {b.pid: len(b.raw) for b in bots}
            planted: dict[str, set[int]] = {}
            await host.send(t="start", game=game)
            if game == "frenemy":
                await play_frenemy(host, bots, rng)
            elif game == "alibi":
                await play_alibi(host, bots, rng)
            else:
                await play_price(host, bots, planted)
            await all_until(bots, lambda s: s["room"]["phase"] == "results", f"{game} results")
            after = totals(host)
            check(sum(after.values()) > sum(before.values()), f"{game}: session scores did not go up")
            frames = check_frames(bots, game, start, planted)
            for b in bots:
                bad = [e for e in b.errors if e not in EXPECTED_ERRORS]
                check(not bad, f"{b.name} got unexpected errors: {bad}")
            gained = sum(after.values()) - sum(before.values())
            hidden = sum(len(v) for v in planted.values())
            note = f", {hidden} planted guesses never leaked" if hidden else ""
            print(f"OK {game}: {frames} frames checked, +{gained} points{note}")
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
    args = ap.parse_args()
    if not 3 <= args.bots <= 7:
        ap.error("--bots must be 3-7 (Alibi needs 4 players, rooms hold 8)")
    try:
        asyncio.run(run(args.base, args.bots, args.seed))
    except Check as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("ALL GAMES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
