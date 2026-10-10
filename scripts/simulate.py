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
# Per game: a Chicken Run tap that lands just after the bomb is refused, and that's the point.
EXPECTED_BY_GAME = {
    "chicken": {"too_late", "wrong_phase"},
    "lastcard": {"no_catch"},
    "bomb": {"not_yours", "used"},
}

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
for _phase in ("play", "hand_over", "final"):
    ALLOWED_KEYS[("lastcard", _phase)] = (
        {"game", "phase", "round", "rounds", "remaining", "players"}
        | {"order", "turn", "direction", "top", "color", "pending", "stacking", "counts", "deck", "protected"}
        | {"vulnerable", "log", "you", "winner", "scores"}
        | ({"hands"} if _phase != "play" else set())
        | ({"history"} if _phase == "final" else set())
    )
for _phase in ("play", "final"):
    ALLOWED_KEYS[("ludo", _phase)] = {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
    } | {
        "teams",
        "turn_color",
        "turn",
        "rolled",
        "sixes",
        "movable",
        "log",
        "you",
        "winner",
        "places",
        "partners",
        "scores",
    }
for _phase in ("play", "final"):
    ALLOWED_KEYS[("chess", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "board",
        "fen",
        "turn",
        "sides",
        "mover",
        "check",
        "last",
        "history",
        "captured",
        "clocks",
        "increment",
        "draw_offer",
        "result",
        "you",
        "scores",
    }
for _phase in ("choose", "draw", "reveal", "final"):
    ALLOWED_KEYS[("drawguess", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "order",
        "drawer",
        "seconds",
        "word",
        "pattern",
        "choices",
        "guessed",
        "gained",
        "feed",
        "ink",
        "you",
        "scores",
        "history",
    }
for _phase in ("write", "draw", "describe", "album", "final"):
    ALLOWED_KEYS[("telephone", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "order",
        "seconds",
        "done",
        "task",
        "ink",
        "you",
        "scores",
        "album",
        "books",
    }
for _phase in ("roll", "buy", "auction", "manage", "debt", "final"):
    ALLOWED_KEYS[("tycoon", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "board",
        "order",
        "current",
        "dice",
        "doubles",
        "cash",
        "worth",
        "pos",
        "jail",
        "cards",
        "out",
        "owner",
        "houses",
        "mortgaged",
        "offer",
        "auction",
        "debt",
        "raisable",
        "trades",
        "bank",
        "call_it",
        "ends_in",
        "log",
        "you",
        "scores",
    }
for _phase in ("play", "reveal", "final"):
    ALLOWED_KEYS[("wordrace", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "hard",
        "tries",
        "boards",
        "solved",
        "gained",
        "you",
        "answer",
        "wins",
        "history",
    }
for _phase in ("spin", "choose", "perform", "vote", "result", "final"):
    ALLOWED_KEYS[("truthdare", _phase)] = (
        {"game", "phase", "round", "rounds", "remaining", "players"}
        | {
            "heat",
            "target",
            "choice",
            "prompt",
            "voted",
            "voters",
            "you_voted",
            "rerolls",
            "chickens",
            "stats",
        }
        | {"result", "up_next", "history"}
    )
for _phase in ("wait", "go", "result", "final"):
    ALLOWED_KEYS[("reflex", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "fake",
        "early",
        "tapped",
        "result",
        "scores",
        "you",
        "best",
        "wins",
    }
for _phase in ("pass", "boom", "final"):
    ALLOWED_KEYS[("bomb", _phase)] = {"game", "phase", "round", "remaining", "players"} | {
        "order",
        "lives",
        "out",
        "holder",
        "prompt",
        "answers",
        "count",
        "boom",
        "passes",
        "winner",
        "scores",
        "blasts",
    }
for _phase in ("roles", "night", "dawn", "day", "verdict", "final"):
    ALLOWED_KEYS[("mafia", _phase)] = {"game", "phase", "round", "remaining", "players"} | {
        "alive",
        "dead",
        "counts",
        "acted",
        "votes",
        "news",
        "winner",
        "roles",
        "you",
        "log",
        "scores",
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
    "palifico",
    "bid",
    "turn",
    "you",
    "out",
    "history",
}
ALLOWED_KEYS[("split", "choose")] = {"game", "phase", "round", "rounds", "remaining", "players", "pairs"} | {
    "bye",
    "golden",
    "golden_pot",
    "locked",
    "said",
    "lines",
    "record",
    "you",
}
ALLOWED_KEYS[("split", "talk")] = ALLOWED_KEYS[("split", "choose")]
for _phase in ("ready", "run"):
    ALLOWED_KEYS[("chicken", _phase)] = {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
        "base",
    } | {
        "growth",
        "started_ago",
        "cashed",
        "insured",
        "costs",
        "you",
    }
for _phase in ("answer", "bet"):
    ALLOWED_KEYS[("wits", _phase)] = {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
        "question",
    } | {
        "answered",
        "board",
        "bet_in",
        "chips",
        "chip_value",
        "all_in",
        "you",
    }
for _phase in ("set", "crack"):
    ALLOWED_KEYS[("codes", _phase)] = {
        "game",
        "phase",
        "round",
        "rounds",
        "remaining",
        "players",
        "length",
    } | {
        "symbols",
        "set",
        "cracked",
        "guess_counts",
        "hint_counts",
        "decoy_sprung",
        "hint_cost",
        "max_hints",
        "you",
    }
ALLOWED_KEYS[("roulette", "bet")] = {"game", "phase", "round", "rounds", "remaining", "players", "chips"} | {
    "stakes",
    "max_bets",
    "commit",
    "locked_count",
    "spins",
    "audit_cost",
    "you",
}
ALLOWED_KEYS[("lonely", "pick")] = {"game", "phase", "round", "rounds", "remaining", "players", "top"} | {
    "pot",
    "rollover",
    "locked",
    "you",
    "wins",
}
ALLOWED_KEYS[("boxes", "peek")] = {"game", "phase", "round", "rounds", "remaining", "players", "labels"} | {
    "current",
    "coins",
    "boxes",
    "claims_list",
    "you",
}
ALLOWED_KEYS[("boxes", "auction")] = ALLOWED_KEYS[("boxes", "peek")] | {"high", "bids", "claims"}
for _phase in ("teams", "clue", "guess"):
    ALLOWED_KEYS[("codewords", _phase)] = {"game", "phase", "round", "rounds", "remaining", "players"} | {
        "teams",
        "spymasters",
        "turn",
        "board",
        "left",
        "starting",
        "clue",
        "guesses_left",
        "guessed_this_turn",
        "log",
        "pace",
        "you",
        "valid_teams",
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
        self.ink: list[dict[str, Any]] = []  # drawing frames (Draw & Guess)
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
                elif msg.get("t") == "ink":
                    self.ink.append(msg)
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
        # The server closes sockets that exceed 8 msg/s (burst 16) with 4008. Bots run at machine
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
                (bid["qty"] + 1, bid["face"])  # palifico: the face is fixed
                if bid and g["palifico"]
                else (bid["qty"], bid["face"] + 1)
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


async def play_split(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Random choices and lines; a choice must never show up in anyone else's frame before the reveal."""
    for rnd in range(1, 6):
        await all_until(bots, game_is("split", "talk", rnd), f"split talk {rnd}")
        g = host.state["game"]  # type: ignore[index]
        golden = g["golden"]
        check(golden == (rnd == 5), "split: the Golden Pot must be the last round")
        playing = [b for b in bots if golden or b.state["game"]["you"]["partner"] is not None]  # type: ignore[index]
        for b in playing:
            if rng.random() < 0.5:
                await b.send(t="act", a="say", line=rng.randrange(len(g["lines"])))
        await skip(host)
        await all_until(bots, game_is("split", "choose", rnd), f"split choose {rnd}")
        picks: dict[str, str] = {}
        for b in playing:
            picks[b.pid] = rng.choice(["split", "steal"])
            await b.send(t="act", a="choose", choice=picks[b.pid])
        await all_until(bots, game_is("split", "reveal", rnd), f"split reveal {rnd}")
        for b in bots:
            for raw in b.raw:
                gg = json.loads(raw).get("game") or {}
                if gg.get("game") == "split" and gg.get("phase") == "choose" and gg.get("round") == rnd:
                    check(
                        gg["you"]["choice"] in (None, picks.get(b.pid)),
                        f"{b.name} saw a choice that isn't theirs",
                    )
        r = host.state["game"]["result"]  # type: ignore[index]
        for pr in r["pairs"]:
            check(all(pr["choices"][p] == picks[p] for p in pr["players"]), "split: revealed choices != sent")
        if golden:
            check(r["golden"]["choices"] == picks, "split: golden choices != sent")
        await skip(host)


def split_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for h in history:
        for pr in h["pairs"]:
            a, b = pr["players"]
            ca, cb, pot = pr["choices"][a], pr["choices"][b], pr["pot"]
            if ca == cb == "split":
                pts[a] += pot // 2
                pts[b] += pot // 2
            elif ca != cb:
                pts[a if ca == "steal" else b] += pot
        if h["bye"]:
            pts[h["bye"]] += 50
        if h.get("golden"):
            gold = h["golden"]
            thieves = [p for p, c in gold["choices"].items() if c == "steal"]
            for p in gold["choices"]:
                if not thieves:
                    pts[p] += gold["pot"] // len(gold["choices"])
                elif thieves == [p]:
                    pts[p] += gold["pot"]
    return pts


async def play_chicken(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots bail at random moments (some hold on). The bomb must never show before it goes off, every
    banked value must follow the published formula, and no run frame may carry a countdown."""
    for rnd in range(1, 6):
        await all_until(bots, game_is("chicken", "ready", rnd), f"chicken ready {rnd}")
        for b in bots:  # dirty tricks before the run
            if rng.random() < 0.3:
                await b.send(t="act", a="insure")
            if rng.random() < 0.2 and not b.state["game"]["you"]["fuse_used"]:  # type: ignore[index]
                await b.send(t="act", a="fuse", target=rng.choice([o.pid for o in bots if o is not b]))
        await host.send(t="ping")  # a round trip, so every trick has landed before the skip
        await asyncio.sleep(0.5)
        await skip(host)
        await all_until(bots, game_is("chicken", "run", rnd), f"chicken run {rnd}")
        order = bots[:]
        rng.shuffle(order)
        start = asyncio.get_running_loop().time()
        for b in order:
            wait = rng.uniform(0.2, 9.0)
            delay = start + wait - asyncio.get_running_loop().time()
            if delay > 0:
                await asyncio.sleep(delay)
            if (host.state["game"] or {}).get("phase") != "run":  # type: ignore[union-attr]
                break
            await b.send(t="act", a="cash")

        # The boom only lasts a few seconds before the next round (or the end): don't require every bot
        # to catch it, just that the round is over, and read its result from the history.
        def over(st: dict[str, Any], rnd: int = rnd) -> bool:
            gg = st.get("game") or {}
            return gg.get("phase") in ("boom", "final") or gg.get("round", 0) > rnd

        await host.until(over, f"chicken boom {rnd}")
        # Each round's result is checked from the final history below: frames are "latest state
        # wins", so a busy socket can legitimately skip straight from the run to the next round.
        for b in bots:
            for raw in b.raw:
                gg = json.loads(raw).get("game") or {}
                if (
                    gg.get("game") == "chicken"
                    and gg.get("round") == rnd
                    and gg.get("phase") in ("ready", "run")
                ):
                    check("result" not in gg, f"{b.name} saw the bomb early")
                    if gg["phase"] == "run":
                        check(gg["remaining"] is None, f"{b.name} got a countdown during the run")
        if host.state["game"]["phase"] == "boom":  # type: ignore[index]
            await skip(host)
    await host.until(lambda st: (st.get("game") or {}).get("phase") == "final", "chicken final")
    history = host.state["game"]["history"]  # type: ignore[index]
    check(len(history) == 5, f"chicken: {len(history)} rounds in the history, expected 5")
    for r in history:
        for pid, c in r["cashed"].items():
            check(c["value"] == int(20 * 1.15 ** c["t"]), f"chicken: {pid} banked {c['value']} at {c['t']}s")
            check(c["t"] <= r["bomb"], "chicken: a cash-out after the bomb was accepted")


def chicken_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for h in history:
        for pid, c in h["cashed"].items():
            pts[pid] += c["value"]
        if h["nerve"]:
            pts[h["nerve"]] += 50
        for pid, x in h["extras"].items():  # insurance payouts minus tricks bought
            pts[pid] += x
    return pts


async def play_wits(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Unique, odd, large answers (nothing else in a frame looks like them), so if one shows up in someone
    else's frame before the board, it's a leak. Bets go on random slots; scoring is checked exactly."""
    for rnd in range(1, 7):
        await all_until(bots, game_is("wits", "answer", rnd), f"wits answer {rnd}")
        # Odd bots answer 1 (at or under nearly every true answer, so real answers win too); even bots
        # answer big unique values that the leak check below can spot unambiguously.
        mine = {b.pid: 1 if i % 2 else 7_000_001 + 2 * (rnd * 100 + i) for i, b in enumerate(bots)}
        for b in bots:
            await b.send(t="act", a="answer", value=mine[b.pid])
        await all_until(bots, game_is("wits", "bet", rnd), f"wits bet {rnd}")
        for b in bots:
            for raw in b.raw:
                gg = json.loads(raw).get("game") or {}
                if gg.get("game") == "wits" and gg.get("phase") == "answer" and gg.get("round") == rnd:
                    others = {v for pid, v in mine.items() if pid != b.pid and v > 1}
                    check(not (others & set(values(gg))), f"{b.name} saw another answer before the board")
        n = len(host.state["game"]["board"])  # type: ignore[index]
        for b in bots:
            if rnd == 6:  # all in: one slot, a wager of the bot's own points
                top = b.state["game"]["you"]["max_wager"]  # type: ignore[index]
                await b.send(t="act", a="bet", slots=[rng.randrange(n)], wager=rng.randint(0, top))
            else:
                await b.send(t="act", a="bet", slots=[rng.randrange(n), rng.randrange(n)])
        await all_until(bots, game_is("wits", "reveal", rnd), f"wits reveal {rnd}")
        await skip(host)


def wits_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for h in history:
        for pid, g in h["gains"].items():
            pts[pid] += g
    return pts


def mastermind(code: list[int], guess: list[int]) -> tuple[int, int]:
    hits = sum(a == b for a, b in zip(code, guess, strict=True))
    common = sum(min(code.count(x), guess.count(x)) for x in set(guess))
    return hits, common - hits


async def play_codes(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots hide random codes, then crack each other with a consistent-guess solver (every guess fits all
    feedback so far). After the reveal every piece of feedback must match the revealed codes."""
    from itertools import product

    await all_until(bots, game_is("codes", "set"), "codes set")
    for b in bots:
        await b.send(t="act", a="set", code=[rng.randrange(6) for _ in range(4)], decoy=rng.random() < 0.5)
    await all_until(bots, game_is("codes", "crack"), "codes crack")
    every = [list(c) for c in product(range(6), repeat=4)]

    async def crack(b: Bot) -> None:
        for target in [o for o in bots if o is not b]:
            for _ in range(12):
                g = b.state["game"]  # type: ignore[index]
                if g["phase"] != "crack" or b.pid in g["cracked"][target.pid]:
                    break
                seen = [h for h in g["you"]["guesses"].get(target.pid, []) if not h.get("decoy")]
                hints = g["you"]["hints"].get(target.pid, [])
                if not hints and rng.random() < 0.3:
                    await b.send(t="act", a="hint", target=target.pid)
                    await b.until(lambda s, t=target.pid: bool(s["game"]["you"]["hints"].get(t)), "hint")
                    continue
                fits = [
                    c
                    for c in every
                    if all(mastermind(c, h["code"]) == (h["hits"], h["near"]) for h in seen)
                    and all(c[h["pos"]] == h["symbol"] for h in hints)
                ] or every  # an unflagged decoy answer can leave nothing consistent for a moment
                n = len(g["you"]["guesses"].get(target.pid, []))
                await b.send(t="act", a="guess", target=target.pid, code=rng.choice(fits))
                await b.until(
                    lambda s, n=n, t=target.pid: (
                        len((s["game"] or {}).get("you", {}).get("guesses", {}).get(t, [])) > n
                        or (s["game"] or {}).get("phase") != "crack"
                    ),
                    "guess answered",
                )
                await asyncio.sleep(1.6)  # the server's cooldown is 1.5 s

    await asyncio.gather(*(crack(b) for b in bots))
    if host.state["game"]["phase"] == "crack":  # type: ignore[index]
        await skip(host)
    await all_until(bots, game_is("codes", "final"), "codes final")
    codes = host.state["game"]["codes"]  # type: ignore[index]
    for b in bots:
        for target, gs in b.state["game"]["you"]["guesses"].items():  # type: ignore[index]
            for h in gs:
                if h.get("decoy"):  # a decoy answer must not be the real one's, and never a fake crack
                    check(h["hits"] < 4, "codes: a decoy faked a crack")
                    continue
                check(mastermind(codes[target], h["code"]) == (h["hits"], h["near"]), "codes: wrong feedback")
        for target, hs in b.state["game"]["you"]["hints"].items():  # type: ignore[index]
            for h in hs:
                check(codes[target][h["pos"]] == h["symbol"], "codes: a hint lied")


def codes_points(cracked: dict[str, list[str]], ids: list[str], hints: dict[str, int]) -> dict[str, int]:
    pts = {pid: -50 * hints.get(pid, 0) for pid in ids}
    for owner, who in cracked.items():
        for i, pid in enumerate(who):
            pts[pid] += (300, 200)[i] if i < 2 else 100
        if not who:
            pts[owner] += 200
    return pts


async def play_roulette(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Exactly one bot is told it's the House each spin; nobody else learns who before the spin; every
    spin matches its commitment."""
    kinds = ["red", "black", "odd", "even", "low", "high"]
    for rnd in range(1, 7):
        await all_until(bots, game_is("roulette", "bet", rnd), f"roulette bet {rnd}")
        houses = [b for b in bots if b.state["game"]["you"]["is_house"]]  # type: ignore[index]
        check(len(houses) == 1, f"roulette: {len(houses)} bots told they're the House")
        commit = host.state["game"]["commit"]  # type: ignore[index]
        for b in bots:
            chips = b.state["game"]["chips"][b.pid]  # type: ignore[index]
            bets = []
            if chips >= 100:
                bets = [
                    {"kind": rng.choice(kinds), "amount": 50},
                    {"kind": "number", "value": rng.randrange(37), "amount": 50},
                ]
            others = [o.pid for o in bots if o is not b]
            you = b.state["game"]["you"]  # type: ignore[index]
            tricks = {"rig": rng.random() < 0.5} if you["can_rig"] else {"audit": rng.random() < 0.3}
            await b.send(t="act", a="lock", bets=bets, accuse=rng.choice(others), **tricks)
        await all_until(bots, game_is("roulette", "spin", rnd), f"roulette spin {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        check(r["house"] == houses[0].pid, "roulette: the revealed House isn't the one that was told")
        proof = hashlib.sha256(f"{r['fair_number']}:{r['nonce']}".encode()).hexdigest()
        check(proof == commit == r["commit"], "roulette: the fair spin doesn't match its commitment")
        check(r["rigged"] or r["number"] == r["fair_number"], "roulette: an unrigged spin moved")
        check(r["caught"] == (r["rigged"] and bool(r["audits"])), "roulette: audit outcome is wrong")
        check(
            r["house_net"] == -sum(r["net"].values()), "roulette: the House didn't take what the table lost"
        )
        for b in bots:
            for raw in b.raw:
                gg = json.loads(raw).get("game") or {}
                if gg.get("game") == "roulette" and gg.get("phase") == "bet" and gg.get("round") == rnd:
                    check("result" not in gg, f"{b.name} saw the spin early")
                    if b is not houses[0]:
                        check(not gg["you"]["is_house"], f"{b.name} was told it's the House")
        await skip(host)


async def play_lonely(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Random picks; nobody sees another pick before the reveal; the winner follows the rule."""
    start = {b.pid: len(b.raw) for b in bots}
    sent: dict[int, dict[str, int]] = {}
    for rnd in range(1, 9):
        await all_until(bots, game_is("lonely", "pick", rnd), f"lonely pick {rnd}")
        sent[rnd] = {}
        for b in bots:
            sent[rnd][b.pid] = rng.randint(1, 6)  # a small range, so collisions happen
            await b.send(t="act", a="pick", n=sent[rnd][b.pid])
        await all_until(bots, game_is("lonely", "reveal", rnd), f"lonely reveal {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        check(r["picks"] == sent[rnd], "lonely: revealed picks != sent")
        lonely = [n for n in r["picks"].values() if list(r["picks"].values()).count(n) == 1]
        want = None if not lonely else next(p for p, n in r["picks"].items() if n == min(lonely))
        check(r["winner"] == want, f"lonely: winner {r['winner']} != {want}")
        await skip(host)
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") == "lonely" and gg.get("phase") == "pick":
                check(gg["you"]["pick"] in (None, sent[gg["round"]][b.pid]), f"{b.name} saw another pick")


async def play_reflex(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Some bots jump the gun (out of the round, -50); the rest tap after the signal, one after another,
    and must be ranked in that order: 100, 60, 40, then 20. No frame says when the signal will come."""
    start = {b.pid: len(b.raw) for b in bots}
    rounds = host.state["game"]["rounds"]  # type: ignore[index]
    want = dict.fromkeys((b.pid for b in bots), 0)
    for rnd in range(1, rounds + 1):
        await all_until(bots, game_is("reflex", "wait", rnd), f"reflex wait {rnd}")
        early = [b for b in bots if rng.random() < 0.2][: len(bots) - 1]
        for b in early:
            await b.send(t="act", a="tap")
            want[b.pid] -= 50
        await all_until(bots, lambda st, k=len(early): len(st["game"]["early"]) == k, "reflex early")
        await skip(host)  # the signal, now
        await all_until(bots, game_is("reflex", "go", rnd), f"reflex go {rnd}")
        rest = [b for b in bots if b not in early]
        rng.shuffle(rest)
        for i, b in enumerate(rest):
            await b.send(t="act", a="tap")
            await all_until(
                bots,
                lambda st, k=i + 1, r=rnd: st["game"]["phase"] == "result" or len(st["game"]["tapped"]) >= k,
                "reflex tap",
            )
            want[b.pid] += (100, 60, 40)[i] if i < 3 else 20
        await all_until(bots, game_is("reflex", "result", rnd), f"reflex result {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        check(list(r["times"]) == [b.pid for b in rest], "reflex: the ranking isn't the order they tapped in")
        check(sorted(r["early"]) == sorted(b.pid for b in early), "reflex: wrong false starts")
        check(list(r["times"].values()) == sorted(r["times"].values()), "reflex: times aren't fastest first")
        check(host.state["game"]["scores"] == want, f"reflex: scores != {want}")  # type: ignore[index]
        await skip(host)
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "reflex":
                continue
            blob = json.dumps(gg)
            check("go_at" not in blob and "fakes" not in blob, f"reflex: {b.name} was told the schedule")
            if gg["phase"] in ("wait", "go"):
                check(gg["remaining"] is None, f"reflex: {b.name} saw a countdown to the signal")
                check(gg["result"] is None, f"reflex: {b.name} saw the result early")


async def play_bomb(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """The holder answers and the bomb moves to the next player still in; a repeat or a non-holder is
    refused; the host's skip sets it off, which costs the holder a life. No frame ever carries the fuse."""
    by_id = {b.pid: b for b in bots}
    start = {b.pid: len(b.raw) for b in bots}
    word = 0
    for _ in range(60):
        await all_until(bots, lambda st: st["game"]["phase"] in ("pass", "final"), "bomb live")
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] == "final":
            break
        rnd, order = g["round"], g["order"]
        for _ in range(rng.randint(0, 3)):
            g = host.state["game"]  # type: ignore[index]
            holder = g["holder"]
            alive = [p for p in order if g["lives"][p] > 0]
            other = next((p for p in alive if p != holder), None)
            if other and rng.random() < 0.3:
                await by_id[other].send(t="act", a="answer", text="not my turn")  # refused: not_yours
            word += 1
            await by_id[holder].send(t="act", a="answer", text=f"thing {word}")
            i = order.index(holder)
            want = next(p for p in order[i + 1 :] + order[: i + 1] if p in alive)
            await all_until(
                bots,
                lambda st, w=want, n=word: (
                    st["game"]["count"] >= 1
                    and st["game"]["holder"] == w
                    and st["game"]["answers"][-1]["text"] == f"thing {n}"
                ),
                "bomb passed",
            )
            if rng.random() < 0.3:
                await by_id[want].send(t="act", a="answer", text=f"THING  {word}!")  # refused: used
        g = host.state["game"]  # type: ignore[index]
        holder, lives = g["holder"], g["lives"][g["holder"]]
        await skip(host)
        await all_until(
            bots, lambda st, r=rnd: st["game"]["phase"] == "boom" and st["game"]["round"] == r, "bomb boom"
        )
        g = host.state["game"]  # type: ignore[index]
        check(g["boom"]["who"] == holder, "bomb: it blew up on someone who wasn't holding it")
        check(g["lives"][holder] == lives - 1, "bomb: the blast didn't cost exactly one life")
        check(g["boom"]["out"] == (lives == 1), "bomb: out flag is wrong")
        await skip(host)
    g = host.state["game"]  # type: ignore[index]
    check(g["phase"] == "final", "bomb: the game didn't end")
    left = [p for p, n in g["lives"].items() if n > 0]
    check(left == [g["winner"]], f"bomb: winner {g['winner']} but {left} still have lives")
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "bomb":
                continue
            check("fuse" not in json.dumps(gg), f"bomb: {b.name} was sent the fuse")
            if gg["phase"] == "pass":
                check(gg["remaining"] is None, f"bomb: {b.name} saw a countdown while the bomb was live")


async def play_mafia(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Random nights and days until someone wins. Every frame is checked: nobody alive sees another
    role, night choices or the Detective's findings; a removed player's role becomes public; ghosts and
    the final screen see everything. The night's result must follow from what the bots sent."""
    by_id = {b.pid: b for b in bots}
    start = {b.pid: len(b.raw) for b in bots}
    await all_until(bots, game_is("mafia", "roles"), "mafia roles")
    role = {b.pid: b.state["game"]["you"]["role"] for b in bots}  # type: ignore[index]
    mafia = {p for p, r in role.items() if r == "mafia"}
    check(len(mafia) == (2 if len(bots) >= 7 else 1), f"mafia: {len(mafia)} Mafia for {len(bots)} players")
    for b in bots:
        mates = set(b.state["game"]["you"]["mates"])  # type: ignore[index]
        check(
            mates == (mafia - {b.pid} if b.pid in mafia else set()), f"mafia: {b.name} got the wrong partners"
        )
    await skip(host)
    last_protected = None
    for _ in range(40):
        await all_until(bots, lambda st: st["game"]["phase"] in ("night", "final"), "mafia night")
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] == "final":
            break
        alive = list(g["alive"])
        picks: dict[str, str] = {}
        for pid in alive:
            options = [
                t
                for t in alive
                if (t != pid or role[pid] == "doctor")
                and not (role[pid] == "mafia" and t in mafia)
                and not (role[pid] == "doctor" and t == last_protected)
            ]
            picks[pid] = rng.choice(options)
            await by_id[pid].send(t="act", a="night", target=picks[pid])
        await all_until(bots, lambda st: st["game"]["phase"] == "dawn", "mafia dawn")
        news = host.state["game"]["news"]  # type: ignore[index]
        wanted = {picks[m] for m in alive if m in mafia}
        doctor = next((p for p in alive if role[p] == "doctor"), None)
        protected = picks.get(doctor) if doctor else None
        if news["killed"]:
            check(news["killed"] in wanted, "mafia: someone the Mafia didn't pick was removed")
            check(news["killed"] != protected, "mafia: the protected player was removed")
            check(news["role"] == role[news["killed"]], "mafia: the wrong role was revealed")
        else:
            check(news["saved"] and bool(wanted & {protected}), "mafia: nobody was removed and nobody saved")
        last_protected = protected
        detective = next((p for p in alive if role[p] == "detective"), None)
        if detective:
            found = by_id[detective].state["game"]["you"]["findings"]  # type: ignore[index]
            check(found.get(picks[detective]) == (picks[detective] in mafia), "mafia: a wrong finding")
        await skip(host)
        await all_until(bots, lambda st: st["game"]["phase"] in ("day", "final"), "mafia day")
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] == "final":
            break
        alive = list(g["alive"])
        votes = {pid: rng.choice([None, *[t for t in alive if t != pid]]) for pid in alive}
        for pid, target in votes.items():
            await by_id[pid].send(t="act", a="vote", target=target)
        await all_until(bots, lambda st: st["game"]["phase"] == "verdict", "mafia verdict")
        news = host.state["game"]["news"]  # type: ignore[index]
        tally: dict[str, int] = {}
        for target in votes.values():
            if target:
                tally[target] = tally.get(target, 0) + 1
        top = max(tally.values(), default=0)
        leaders = [t for t, c in tally.items() if c == top]
        skips = sum(v is None for v in votes.values())
        want = leaders[0] if len(leaders) == 1 and top > skips else None
        check(news["out"] == want, f"mafia: voted out {news['out']}, the votes say {want}")
        await skip(host)
    g = host.state["game"]  # type: ignore[index]
    check(g["phase"] == "final" and g["winner"] in ("town", "mafia"), "mafia: the game didn't end")
    check(g["roles"] == role, "mafia: the final roles differ from what was dealt")
    left = [p for p in g["alive"] if p in mafia]
    check((g["winner"] == "town") == (not left), "mafia: the wrong side won")
    for b in bots:
        gone = False
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "mafia":
                continue
            gone = gone or b.pid not in gg["alive"]
            you = gg["you"]
            check(you["role"] == role[b.pid], f"mafia: {b.name}'s role changed")
            if gg["phase"] != "final" and not gone:
                check(gg["roles"] is None, f"mafia: {b.name} saw every role while still in the game")
            check("findings" not in you or role[b.pid] == "detective", f"mafia: {b.name} saw findings")
            check("mate_picks" not in you or role[b.pid] == "mafia", f"mafia: {b.name} saw the Mafia's picks")
            public = {
                k: v
                for k, v in gg.items()
                if k not in ("you", "roles", "counts", "game", "dead", "news", "winner")
            }
            for word in ("mafia", "detective", "doctor"):
                check(f'"{word}"' not in json.dumps(public), f"mafia: {b.name} saw a role in {gg['phase']}")


async def play_truthdare(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Every bot plays its turns (random choice, random votes). Votes stay secret until the result,
    and every result pays exactly what the rules say."""
    by_id = {b.pid: b for b in bots}
    turns = host.state["game"]["rounds"]  # type: ignore[index]
    check(turns == 2 * len(bots), f"truthdare: {turns} turns for {len(bots)} players, expected 2 each")
    for rnd in range(1, turns + 1):
        await all_until(bots, game_is("truthdare", "spin", rnd), f"truthdare spin {rnd}")
        await skip(host)
        await all_until(bots, game_is("truthdare", "choose", rnd), f"truthdare choose {rnd}")
        target = by_id[host.state["game"]["target"]]  # type: ignore[index]
        await target.send(t="act", a="choose", choice=rng.choice(["truth", "dare"]))
        await all_until(bots, game_is("truthdare", "perform", rnd), f"truthdare perform {rnd}")
        check(bool(host.state["game"]["prompt"]), "truthdare: no prompt on the card")  # type: ignore[index]
        await target.send(t="act", a="done")
        await all_until(bots, game_is("truthdare", "vote", rnd), f"truthdare vote {rnd}")
        sent = {b.pid: rng.random() < 0.7 for b in bots if b is not target}
        for pid, like in sent.items():
            await by_id[pid].send(t="act", a="vote", like=like)
        await all_until(bots, game_is("truthdare", "result", rnd), f"truthdare result {rnd}")
        r = host.state["game"]["result"]  # type: ignore[index]
        yes = sum(sent.values())
        check(
            (r["yes"], r["no"]) == (yes, len(sent) - yes),
            f"truthdare: tally {r['yes']}/{r['no']} != votes sent",
        )
        check(r["passed"] == (yes >= len(sent) - yes), "truthdare: a majority decides, ties pass")
        for b in bots:
            for raw in b.raw[-40:]:
                gg = json.loads(raw).get("game") or {}
                if gg.get("game") == "truthdare" and gg.get("phase") == "vote" and gg.get("round") == rnd:
                    check(gg["you_voted"] in (None, sent.get(b.pid)), f"{b.name} saw someone else's vote")
        await skip(host)


def wordle_marks(guess: str, answer: str) -> str:
    """An independent copy of the Wordle colour rule, to cross-check the server."""
    out = ["x"] * 5
    spare: dict[str, int] = {}
    for i in range(5):
        if guess[i] == answer[i]:
            out[i] = "g"
        else:
            spare[answer[i]] = spare.get(answer[i], 0) + 1
    for i in range(5):
        if out[i] != "g" and spare.get(guess[i], 0):
            out[i] = "y"
            spare[guess[i]] -= 1
    return "".join(out)


def word_answers() -> list[str]:
    """The answer pool, so bots can play like people who know English."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.games.content import WORD_ANSWERS

    return list(WORD_ANSWERS)


async def play_wordrace(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots solve like people: every guess fits all the colours they've seen. Letters and the answer
    must stay hidden until the reveal; every colour and every payout is re-derived here."""
    answers = word_answers()
    rounds = host.state["game"]["rounds"]  # type: ignore[index]
    for rnd in range(1, rounds + 1):
        await all_until(bots, game_is("wordrace", "play", rnd), f"wordrace play {rnd}")
        start = {b.pid: len(b.raw) for b in bots}
        sent: dict[str, list[str]] = {b.pid: [] for b in bots}
        pool = {b.pid: list(answers) for b in bots}
        solved_order: list[str] = []
        for turn in range(6):
            for b in bots:
                if b.pid in solved_order or not pool[b.pid]:
                    continue
                guess = rng.choice(pool[b.pid])
                sent[b.pid].append(guess)
                await b.send(t="act", a="guess", word=guess)

                def got(n: int, pid: str = b.pid):
                    return lambda st: len(((st.get("game") or {}).get("boards") or {}).get(pid, [])) >= n

                await b.until(got(len(sent[b.pid])), f"wordrace row {rnd}/{turn}")
                row = b.state["game"]["boards"][b.pid][-1]  # type: ignore[index]
                check(row["word"] == guess, f"wordrace: {b.name}'s own row shows {row['word']}, not {guess}")
                if row["marks"] == "ggggg":
                    solved_order.append(b.pid)
                pool[b.pid] = [w for w in pool[b.pid] if wordle_marks(guess, w) == row["marks"]]
        await all_until(bots, game_is("wordrace", "reveal", rnd), f"wordrace reveal {rnd}")
        g = host.state["game"]  # type: ignore[index]
        answer = g["answer"]
        for b in bots:
            for want, row in zip(sent[b.pid], g["boards"][b.pid], strict=True):
                check(row["word"] == want, "wordrace: the revealed rows don't match the guesses")
                check(
                    row["marks"] == wordle_marks(want, answer),
                    f"wordrace: wrong colours for {want} vs {answer}",
                )
        check(g["solved"] == solved_order, f"wordrace: solve order {g['solved']} != {solved_order}")
        for i, pid in enumerate(g["solved"]):
            want = (7 - len(sent[pid])) * 100 + (100 if i == 0 else 50 if i == 1 else 0)
            check(g["gained"][pid] == want, f"wordrace: {pid} got {g['gained'][pid]}, expected {want}")
        for b in bots:
            for raw in b.raw[start[b.pid] :]:
                gg = json.loads(raw).get("game") or {}
                if gg.get("game") != "wordrace" or gg.get("phase") != "play":
                    continue
                check(gg["answer"] is None, f"{b.name} saw the answer before the reveal")
                for pid, rows in gg["boards"].items():
                    if pid != b.pid:
                        check(all(r["word"] is None for r in rows), f"{b.name} saw {pid}'s letters")
        await skip(host)


def canvas_ops(frames: list[dict[str, Any]], canvas: str) -> list[Any]:
    """The operations a screen has received for one canvas, in order (a full redraw starts over)."""
    ops: list[Any] = []
    for f in frames:
        if f.get("id") != canvas:
            continue
        check(f["n"] <= len(ops), "drawguess: an ink frame skipped ahead")
        ops = ops[: f["n"]] + f["ops"]
    return ops


def phase_is(phase: str):
    return lambda st: (st.get("game") or {}).get("phase") == phase


async def play_drawguess(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Every turn: the artist picks a word and draws a few strokes (which must reach every other screen,
    in order); the others guess, some wrong, some right. The word must stay with the artist (and whoever
    has guessed it) until the reveal, and the three choices with the artist."""
    by_id = {b.pid: b for b in bots}
    g = host.state["game"]  # type: ignore[index]
    for turn in range(g["rounds"] * len(g["order"])):
        await all_until(bots, phase_is("choose"), f"drawguess choose {turn}")
        artist = by_id[host.state["game"]["drawer"]]  # type: ignore[index]
        await artist.until(lambda st: bool(st["game"]["choices"]), "drawguess choices")
        choices = artist.state["game"]["choices"]  # type: ignore[index]
        for b in bots:
            if b is not artist:
                check(b.state["game"]["choices"] is None, f"{b.name} saw the artist's choices")  # type: ignore[index]
        await artist.send(t="act", a="pick", i=rng.randrange(3))
        await all_until(bots, phase_is("draw"), f"drawguess draw {turn}")
        word = artist.state["game"]["word"]  # type: ignore[index]
        check(word in choices, "drawguess: the word isn't one of the choices")
        canvas = artist.state["game"]["ink"]["id"]  # type: ignore[index]
        strokes: list[dict[str, Any]] = [
            {"op": "line", "c": rng.randrange(14), "w": rng.randrange(4), "p": [10, 10, 200, 150]},
            {"op": "more", "p": [rng.randrange(801), rng.randrange(601)] * 30},
            {"op": "undo"},
            {"op": "line", "c": 0, "w": 1, "p": [400, 300]},
        ]
        for op in strokes:
            await artist.send(t="ink", **op)
        guessers = [b for b in bots if b is not artist]
        for b in guessers:
            await b.until(
                lambda st, b=b, c=canvas, n=len(strokes): len(canvas_ops(b.ink, c)) >= n, "drawguess ink"
            )
            check(
                canvas_ops(b.ink, canvas) == strokes,
                f"drawguess: {b.name}'s canvas differs from the artist's",
            )
            check(b.state["game"]["word"] is None, f"{b.name} saw the word before guessing")  # type: ignore[index]
        right = [b for b in guessers if rng.random() < 0.7]
        for b in guessers:
            await b.send(t="act", a="guess", text="definitely not it")
            if b in right:
                await b.send(t="act", a="guess", text=word.upper())
                await b.until(lambda st, b=b: b.pid in st["game"]["guessed"], "drawguess got it")
                check(b.state["game"]["word"] == word, f"{b.name} got it but can't see the word")  # type: ignore[index]
        if len(right) < len(guessers):
            await host.until(lambda st, n=len(right): len(st["game"]["guessed"]) == n, "drawguess guesses in")
            await skip(host)
        await all_until(bots, phase_is("reveal"), f"drawguess reveal {turn}")
        g = host.state["game"]  # type: ignore[index]
        check(g["word"] == word, "drawguess: the reveal shows a different word")
        check(set(g["guessed"]) == {b.pid for b in right}, "drawguess: wrong guessers")
        check(g["gained"].get(artist.pid, 0) == 75 * len(right), "drawguess: the artist's points are off")
        for b in right:
            check(100 <= g["gained"][b.pid] <= 400, f"drawguess: {b.name} got {g['gained'][b.pid]}")
        await skip(host)
    await all_until(bots, phase_is("final"), "drawguess over")


async def play_telephone(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Every step, each bot works from the page the previous player made: the sentence to draw must be
    exactly what they wrote, the drawing to describe exactly what they drew (fetched by id). Nobody may
    receive a stroke while drawings are made, or see another book before the album. In the album the
    bots like pages; the scores must equal 100 per like."""
    by_id = {b.pid: b for b in bots}
    order = host.state["game"]["order"]  # type: ignore[index]
    n = len(order)
    start = {b.pid: len(b.raw) for b in bots}
    ink_start = {b.pid: len(b.ink) for b in bots}
    made: dict[tuple[int, int], Any] = {}  # (book, step) -> text or drawing ops
    author: dict[tuple[int, int], str] = {}  # (book, step) -> who made that page
    senders: dict[str, list[str]] = {p: [] for p in order}  # whose pages each player was handed
    for step in range(n):
        phase = "write" if step == 0 else "draw" if step % 2 else "describe"
        await all_until(bots, phase_is(phase), f"telephone {phase} {step}")
        held: set[int] = set()
        for j, pid in enumerate(order):
            b = by_id[pid]
            task = b.state["game"]["task"]  # type: ignore[index]
            if step:
                check("from" not in task, "telephone: a page named its author during play")
            # Which book is this? The one whose last page is exactly what this bot was handed.
            book = j
            if phase == "draw":
                book = next((bk for bk in range(n) if made.get((bk, step - 1)) == task["prompt"]), -1)
                check(book >= 0, f"telephone: {b.name} got a sentence nobody wrote")
            elif phase == "describe":
                drawing = task["drawing"]
                await b.send(t="inksync", id=drawing)

                def got(_st: dict[str, Any], b: Bot = b, d: str = drawing) -> bool:
                    return any(f.get("id") == d and f.get("full") for f in b.ink)

                await b.until(got, "telephone drawing")
                frame = next(f for f in reversed(b.ink) if f.get("id") == drawing and f.get("full"))
                book = next((bk for bk in range(n) if made.get((bk, step - 1)) == frame["ops"]), -1)
                check(book >= 0, f"telephone: {b.name} got a drawing nobody drew")
            check(book not in held, f"telephone: two players hold book {book}")
            check(
                pid not in [author.get((book, s)) for s in range(step)],
                f"telephone: {b.name} got a book twice",
            )
            if step:
                senders[pid].append(author[(book, step - 1)])
            held.add(book)
            author[(book, step)] = pid
            if phase == "draw":
                ops = [
                    {
                        "op": "line",
                        "c": rng.randrange(14),
                        "w": rng.randrange(4),
                        "p": [rng.randrange(801), 300, 5, 5],
                    },
                    {"op": "more", "p": [rng.randrange(801), rng.randrange(601)] * 5},
                ]
                for op in ops:
                    await b.send(t="ink", **op)
                made[(book, step)] = ops
                await b.send(t="act", a="done")
            else:
                text = f"{'start' if step == 0 else 'saw'} {rng.randrange(10**6)} by {b.name}"
                made[(book, step)] = text
                await b.send(t="act", a="text", text=text)
    await all_until(bots, phase_is("album"), "telephone album")
    for pid, got_from in senders.items():
        repeats = len(got_from) - len(set(got_from))
        check(repeats <= (0 if n % 2 == 0 else 1), f"telephone: {pid} kept getting the same person's pages")
    for b in bots:
        relayed = [f for f in b.ink[ink_start[b.pid] :] if not f.get("full")]
        check(not relayed, f"telephone: {b.name} received someone's strokes while they drew")
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "telephone" or gg.get("phase") not in ("write", "draw", "describe"):
                continue
            mine = gg["task"] or {}
            for (_book, _step), page in made.items():
                if isinstance(page, str) and page not in (mine.get("prompt"), mine.get("text")):
                    check(page not in raw, f"telephone: {b.name} saw a page of another book")
    # The album: every page, in order; bots like a few (never their own).
    likes: dict[str, int] = dict.fromkeys(order, 0)
    for book in range(n):
        for entry in range(n):
            await host.until(
                lambda st, bk=book, e=entry: (
                    (st["game"].get("album") or {}).get("book") == bk and st["game"]["album"]["entry"] == e
                ),
                "telephone page",
            )
            page = host.state["game"]["album"]["pages"][entry]  # type: ignore[index]
            want = made[(book, entry)]
            if isinstance(want, str):
                check(page["text"] == want, "telephone: the album shows the wrong words")
            page_by = author[(book, entry)]
            shown = host.state["game"]["album"]["pages"]  # type: ignore[index]
            if entry < n - 1:
                check(all(pg["by"] is None for pg in shown), "telephone: the album named someone too early")
            else:
                check(all(pg["by"] for pg in shown), "telephone: the finished book didn't name its authors")
            fans = [b for b in bots if b.pid != page_by and rng.random() < 0.4]
            for b in fans:
                await b.send(t="act", a="like", book=book, entry=entry)
            likes[page_by] += len(fans)
            await host.until(
                lambda st, e=entry, k=len(fans): st["game"]["album"]["pages"][e]["likes"] == k,
                "telephone likes",
            )
            await skip(host)
    await all_until(bots, phase_is("final"), "telephone over")
    got = host.state["game"]["books"]  # type: ignore[index]
    total = {p: 0 for p in order}
    for bk in got:
        for pg in bk["pages"]:
            total[pg["by"]] += pg["likes"]
    check(total == likes, f"telephone: likes {total} != sent {likes}")


def tycoon_check(g: dict[str, Any]) -> None:
    """The rules every Property Tycoon frame must keep."""
    board = g["board"]
    owner = {int(k): v for k, v in g["owner"].items()}
    houses = {int(k): v for k, v in g["houses"].items()}
    groups: dict[str, list[int]] = {}
    for sq, sp in enumerate(board):
        if sp["kind"] == "street":
            groups.setdefault(sp["group"], []).append(sq)
    for p in g["order"]:
        check(g["cash"][p] >= 0, f"tycoon: {p} has negative cash")
        worth = g["cash"][p]
        for sq, who in owner.items():
            if who == p:
                price = board[sq]["price"]
                worth += price // 2 if sq in g["mortgaged"] else price
                worth += houses.get(sq, 0) * board[sq].get("house", 0)
        check(g["worth"][p] == worth, f"tycoon: {p}'s worth {g['worth'][p]} != {worth}")
    check(all(v not in g["out"] for v in owner.values()), "tycoon: a bankrupt player still owns property")
    for sq in houses:
        group = groups[board[sq]["group"]]
        check(all(owner.get(s) == owner.get(sq) for s in group), "tycoon: houses without the full set")
        levels = [houses.get(s, 0) for s in group]
        check(max(levels) - min(levels) <= 1, "tycoon: uneven building")
        check(not any(s in g["mortgaged"] for s in group), "tycoon: buildings in a mortgaged set")
    check(sum(h for h in houses.values() if h < 5) <= 32, "tycoon: more than 32 houses")


async def play_tycoon(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots play properly: roll, buy what they can afford, bid, build on full sets, trade now and then,
    raise money or go bankrupt. Every frame is checked against the rules; after 45 turns everyone votes
    to call it a night (or the game ends sooner by bankruptcy)."""
    by_id = {b.pid: b for b in bots}

    def token(st: dict[str, Any]) -> str:
        g = st.get("game") or {}
        keys = (
            "phase",
            "current",
            "cash",
            "owner",
            "houses",
            "mortgaged",
            "auction",
            "debt",
            "trades",
            "call_it",
        )
        return json.dumps([g.get(k) for k in keys] + [len(g.get("log") or []), (g.get("log") or [None])[-1]])

    async def act(b: Bot, **msg: Any) -> None:
        before, errors = token(b.state), len(b.errors)  # type: ignore[arg-type]
        await b.send(t="act", **msg)
        await b.until(lambda st: token(st) != before or len(b.errors) > errors, f"tycoon {msg.get('a')}")
        now = token(b.state)  # type: ignore[arg-type]
        if now != before:
            await all_until(bots, lambda st, t=now: token(st) == t, "tycoon sync")

    async def host_skip() -> None:
        before = token(host.state)  # type: ignore[arg-type]
        await skip(host)
        await host.until(lambda st: token(st) != before, "tycoon skip")
        now = token(host.state)  # type: ignore[arg-type]
        await all_until(bots, lambda st, t=now: token(st) == t, "tycoon sync")

    seen = 0
    for _ in range(3000):
        g = host.state["game"]  # type: ignore[index]
        tycoon_check(g)
        seen += 1
        phase = g["phase"]
        if phase == "final":
            break
        board, owner = g["board"], {int(k): v for k, v in g["owner"].items()}
        alive = [p for p in g["order"] if p not in g["out"]]
        cur = by_id[g["current"]]
        if g["round"] >= 45 and not all(p in g["call_it"] for p in alive):
            for p in alive:
                if p not in g["call_it"]:
                    await act(by_id[p], a="call_it")
                    break
            continue
        if phase == "debt":
            debt, debtor = g["debt"], by_id[g["debt"]["pid"]]
            if g["cash"][debtor.pid] >= debt["amount"]:
                await act(debtor, a="pay_debt")
                continue
            mine = sorted(
                (sq for sq, w in owner.items() if w == debtor.pid), key=lambda sq: board[sq]["price"]
            )
            built = [sq for sq in mine if g["houses"].get(str(sq))]
            if built:
                top = max(built, key=lambda sq: g["houses"][str(sq)])
                await act(debtor, a="sell", square=top)
            elif [sq for sq in mine if sq not in g["mortgaged"]]:
                await act(debtor, a="mortgage", square=next(sq for sq in mine if sq not in g["mortgaged"]))
            else:
                await act(debtor, a="bankrupt")
            continue
        if phase == "auction":
            a = g["auction"]
            bidder = by_id[rng.choice(alive)]
            if a["bid"] < 150 and g["cash"][bidder.pid] > a["bid"] + 100 and rng.random() < 0.6:
                await act(bidder, a="bid", amount=a["bid"] + rng.choice((10, 20, 50)))
            else:
                await host_skip()
            continue
        if phase == "buy":
            price = board[g["offer"]]["price"]
            await act(cur, a="buy" if g["cash"][cur.pid] >= price + 50 and rng.random() < 0.85 else "decline")
            continue
        if phase == "roll":
            if cur.pid in g["jail"] and g["cards"][cur.pid]:
                await act(cur, a="use_card")
            elif cur.pid in g["jail"] and g["cash"][cur.pid] >= 100 and rng.random() < 0.3:
                await act(cur, a="pay_fine")
            else:
                await act(cur, a="roll")
            continue
        # manage: build where possible, sometimes trade, then end the turn
        groups: dict[str, list[int]] = {}
        for sq, sp in enumerate(board):
            if sp["kind"] == "street":
                groups.setdefault(sp["group"], []).append(sq)
        target = None
        for group in groups.values():
            if all(owner.get(sq) == cur.pid for sq in group) and not any(
                sq in g["mortgaged"] for sq in group
            ):
                low = min(group, key=lambda sq: g["houses"].get(str(sq), 0))
                level = g["houses"].get(str(low), 0)
                if level < 5 and g["cash"][cur.pid] > board[low]["house"] + 150:
                    target = low
                    break
        if target is not None:
            await act(cur, a="build", square=target)
            continue
        if rng.random() < 0.15 and len(alive) > 1:
            other = rng.choice([p for p in alive if p != cur.pid])
            theirs = [sq for sq, w in owner.items() if w == other and not g["houses"].get(str(sq))]
            if theirs:
                sq = rng.choice(theirs)
                await act(
                    cur,
                    a="offer",
                    to=other,
                    give={"cash": min(board[sq]["price"], g["cash"][cur.pid])},
                    get={"squares": [sq]},
                )
                tid = next((t["id"] for t in cur.state["game"]["trades"] if t["from"] == cur.pid), None)  # type: ignore[index]
                if tid is not None:
                    await act(by_id[other], a="accept" if rng.random() < 0.5 else "reject", trade=tid)
                continue
        await act(cur, a="end")
    await all_until(bots, phase_is("final"), "tycoon over")
    tycoon_check(host.state["game"])  # type: ignore[index]
    check(seen > 50, "tycoon: the game hardly started")


def tycoon_scores(g: dict[str, Any], ids: list[str]) -> dict[str, int]:
    return {p: g["worth"][p] if p not in g["out"] else g["out"].index(p) + 1 for p in ids}


def telephone_points(books: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    out = dict.fromkeys(ids, 0)
    for bk in books:
        for pg in bk["pages"]:
            out[pg["by"]] += 100 * pg["likes"]
    return out


def drawguess_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    out = dict.fromkeys(ids, 0)
    for h in history:
        for p, v in h["points"].items():
            out[p] += v
    return out


def wordrace_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for h in history:
        for p, v in h["points"].items():
            pts[p] += v
    return pts


def lastcard_points(cards: list[dict[str, Any]]) -> int:
    pts = 0
    for c in cards:
        v = c["value"]
        pts += int(v) if v.isdigit() else 50 if v in ("wild", "wild4") else 20
    return pts


async def play_lastcard(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots play legal cards (and sometimes forget to call LAST CARD, or bluff a Wild Draw Four).
    Nobody may ever see another hand or whether a Draw Four was legal; every hand's score must equal
    the cards left in the others' hands."""
    by_id = {b.pid: b for b in bots}
    start = {b.pid: len(b.raw) for b in bots}
    hands = host.state["game"]["rounds"]  # type: ignore[index]

    def token(st: dict[str, Any]) -> str:
        g = st.get("game") or {}
        keys = ("phase", "round", "turn", "counts", "deck", "pending", "protected", "vulnerable", "color")
        return json.dumps([g.get(k) for k in keys] + [g.get("log", [])[-1:]], sort_keys=True)

    for hand_no in range(1, hands + 1):
        for _ in range(1500):
            g = host.state["game"]  # type: ignore[index]
            if g["phase"] != "play" or g["round"] != hand_no:
                break
            now = token(host.state)  # type: ignore[arg-type]
            bot = by_id[g["turn"]]
            await bot.until(lambda st, t=now: token(st) == t, f"lastcard sync {hand_no}")
            mine = bot.state["game"]  # type: ignore[index]
            you = mine["you"]
            caught = [p for p in mine["vulnerable"] if p != bot.pid]
            if caught and rng.random() < 0.5:
                await bot.send(t="act", a="catch", target=caught[0])
            elif mine["pending"] is not None:
                stack = [c for c in you["hand"] if c["playable"]]
                if stack:
                    await bot.send(t="act", a="play", card=stack[0]["id"])
                elif mine["pending"]["kind"] == "wild4" and rng.random() < 0.4:
                    await bot.send(t="act", a="challenge")
                else:
                    await bot.send(t="act", a="draw")
            elif you["can_last"] and rng.random() < 0.7:
                await bot.send(t="act", a="last")
            else:
                playable = [c for c in you["hand"] if c["playable"]]
                if playable:
                    c = rng.choice(playable)
                    colour = rng.choice(["red", "yellow", "green", "blue"])
                    extra = {"color": colour} if c["color"] == "wild" else {}
                    await bot.send(t="act", a="play", card=c["id"], **extra)
                elif you["drawn"] is not None:
                    await bot.send(t="act", a="pass")
                else:
                    await bot.send(t="act", a="draw")
            await host.until(lambda st, t=now: token(st) != t, f"lastcard move {hand_no}")
        await all_until(
            bots, lambda st: (st.get("game") or {}).get("phase") in ("hand_over", "final"), "lastcard over"
        )
        g = host.state["game"]  # type: ignore[index]
        winner = g["winner"]
        check(g["hands"][winner] == [], f"lastcard: winner {winner} still holds cards")
        teams = host.state.get("teams")  # type: ignore[union-attr]
        side = {p: i for i, ids in enumerate(teams["members"]) for p in ids} if teams else {}
        # Partners (the Teams switch): the winner scores only the other team's cards.
        rivals = [p for p in g["hands"] if p != winner and (not side or side[p] != side[winner])]
        want = sum(lastcard_points(g["hands"][p]) for p in rivals)
        check(g["scores"][winner] >= want, f"lastcard: the winner's score is below this hand's {want}")
        for p, h in g["hands"].items():
            check(len(h) == g["counts"][p], "lastcard: shown hand sizes don't match the counts")
        if g["phase"] == "hand_over":
            await skip(host)
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "lastcard" or gg.get("phase") != "play":
                continue
            check("hands" not in gg, f"{b.name} saw other hands mid-hand")
            check(len(gg["you"]["hand"]) == gg["counts"][b.pid], f"{b.name}'s hand doesn't match their count")
            check(not gg["pending"] or "legal" not in gg["pending"], f"{b.name} saw if a Draw Four was legal")


async def play_ludo(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots roll and move random legal tokens until a colour gets every token home. Ludo has no secrets:
    every frame must be the same board for everyone, apart from their own colour."""
    by_id = {b.pid: b for b in bots}
    start = {b.pid: len(b.raw) for b in bots}

    def token(st: dict[str, Any]) -> str:
        g = st.get("game") or {}
        return json.dumps([g.get(k) for k in ("phase", "turn", "rolled", "teams")] + [g.get("log", [])[-1:]])

    for _ in range(20000):  # play goes on for 2nd and 3rd place: long games
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] != "play":
            break
        now = token(host.state)  # type: ignore[arg-type]
        bot = by_id[g["turn"]]
        await bot.until(lambda st, t=now: token(st) == t, "ludo sync")
        mine = bot.state["game"]  # type: ignore[index]
        if mine["rolled"] is None:
            await bot.send(t="act", a="roll")
        else:
            await bot.send(t="act", a="move", token=rng.choice(mine["movable"]))
        await host.until(lambda st, t=now: token(st) != t, "ludo move")
    await all_until(bots, lambda st: (st.get("game") or {}).get("phase") == "final", "ludo over")
    g = host.state["game"]  # type: ignore[index]
    win = next(t for t in g["teams"] if t["color"] == g["winner"])
    check(all(p == 56 for p in win["tokens"]), "ludo: the winner still has tokens out")
    colour_of = {p: t["color"] for t in g["teams"] for p in t["members"]}

    def public(gg: dict[str, Any]) -> str:
        return json.dumps(
            {k: v for k, v in gg.items() if k not in ("you", "remaining")},
            sort_keys=True,
        )

    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") == "ludo":
                check(gg["you"] == colour_of[b.pid], f"{b.name} was told the wrong colour")
        check(
            public(b.state["game"]) == public(g),
            f"ludo: {b.name} saw a different final board",
        )  # type: ignore[index]


async def play_chess(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Bots play random legal moves (teammates suggest one first) until the game ends, or resign after
    300 moves. A side's suggestions must never reach the other side."""
    by_id = {b.pid: b for b in bots}
    start = {b.pid: len(b.raw) for b in bots}

    def token(st: dict[str, Any]) -> str:
        g = st.get("game") or {}
        return json.dumps([g.get("phase"), g.get("fen"), g.get("mover"), g.get("draw_offer")])

    for i in range(700):
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] != "play":
            break
        now = token(host.state)  # type: ignore[arg-type]
        mover = by_id[g["mover"]]
        await mover.until(lambda st, t=now: token(st) == t, "chess sync")
        legal = mover.state["game"]["you"]["legal"]  # type: ignore[index]
        mates = [by_id[p] for p in g["sides"][g["turn"]] if p != mover.pid]
        if mates and i % 3 == 0:  # a teammate suggests first
            await mates[0].send(t="act", a="suggest", move=rng.choice(legal))
            await mover.until(lambda st: bool(st["game"]["you"]["suggestions"]), "chess suggestion")
        if i >= 300:
            await mover.send(t="act", a="resign")
        else:
            await mover.send(t="act", a="move", move=rng.choice(legal))
        await host.until(lambda st, t=now: token(st) != t, "chess move")
    await all_until(bots, lambda st: (st.get("game") or {}).get("phase") == "final", "chess over")
    g = host.state["game"]  # type: ignore[index]
    side_of = {p: c for c, ps in g["sides"].items() for p in ps}
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "chess" or not gg.get("you"):
                continue
            for s in gg["you"]["suggestions"]:
                check(side_of[s["by"]] == side_of[b.pid], f"{b.name} saw the other side's suggestion")


def chess_scores(g: dict[str, Any], ids: list[str]) -> dict[str, int]:
    r = g["result"]
    out = {}
    for c, ps in g["sides"].items():
        for p in ps:
            out[p] = 100 if r["winner"] is None else 300 if r["winner"] == c else 0
    return {p: out.get(p, 0) for p in ids}


def ludo_scores(g: dict[str, Any], ids: list[str]) -> dict[str, int]:
    pts = {t["color"]: t["points"] for t in g["teams"]}
    return {p: pts[t["color"]] for t in g["teams"] for p in t["members"] if p in ids}


def lastcard_scores(g: dict[str, Any], ids: list[str]) -> dict[str, int]:
    return {p: g["scores"].get(p, 0) for p in ids}


def truthdare_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for h in history:
        pts[h["player"]] += h["points"] + h["bonus"]
        check(h["points"] in (0, 100 if h["kind"] == "truth" else 200), f"truthdare: odd payout {h}")
    return pts


def lonely_points(history: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for h in history:
        if h["winner"]:
            pts[h["winner"]] += h["pot"]
    return pts


async def play_boxes(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Random bids and claims. A box's contents may only show up for its peeker until it is sold."""
    start = {b.pid: len(b.raw) for b in bots}
    await all_until(bots, game_is("boxes", "peek"), "boxes peek")
    peeks = {b.pid: b.state["game"]["you"]["peek"]["box"] for b in bots}  # type: ignore[index]
    await skip(host)
    for rnd in range(1, 7):
        await all_until(bots, game_is("boxes", "auction", rnd), f"boxes auction {rnd}")
        high = 0
        for b in rng.sample(bots, k=len(bots)):
            if rng.random() < 0.3:
                await b.send(t="act", a="say", line=rng.randrange(5))
            coins = b.state["game"]["coins"][b.pid]  # type: ignore[index]
            amount = high + 10 * rng.randint(1, 8)
            if rng.random() < 0.5 and amount <= coins:
                await b.send(t="act", a="bid", amount=amount)
                await host.until(
                    lambda s, a=amount: (s["game"].get("high") or {}).get("amount") == a, "bid lands"
                )
                high = amount
        await skip(host)
        await all_until(bots, game_is("boxes", "sold", rnd), f"boxes sold {rnd}")
        await skip(host)
    await all_until(bots, game_is("boxes", "final"), "boxes final")
    sold = host.state["game"]["boxes"]  # type: ignore[index]
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "boxes" or gg.get("phase") == "final":
                continue
            public = json.dumps({k: v for k, v in gg.items() if k != "you"})
            for i, box in enumerate(sold):
                if gg["boxes"][i] is None:
                    check(box["name"] not in public, f"{b.name} saw box {i} before it was sold")
                    if i != peeks[b.pid]:
                        check(
                            box["name"] not in json.dumps(gg["you"]), f"{b.name} saw a box they didn't peek"
                        )


def boxes_points(sold: list[dict[str, Any]], ids: list[str]) -> dict[str, int]:
    pts = dict.fromkeys(ids, 0)
    for s in sold:
        if s["winner"]:
            pts[s["winner"]] += s["value"] - s["price"]
    return pts


async def play_codewords(host: Bot, bots: list[Bot], rng: random.Random) -> None:
    """Teams are ready-voted in; spymasters clue, guessers reveal random words until a team wins. Only the
    two spymasters may ever see the colour of a face-down word."""
    start = {b.pid: len(b.raw) for b in bots}
    await all_until(bots, game_is("codewords", "teams"), "codewords teams")
    stage = host.state["stage"]  # type: ignore[index]
    for b in bots:
        await b.send(t="ready", stage=stage)
    by_id = {b.pid: b for b in bots}
    clues = iter(f"ZQ{chr(65 + i // 26)}{chr(65 + i % 26)}X" for i in range(600))
    for _ in range(300):
        await host.until(
            lambda s: (s.get("game") or {}).get("phase") in ("clue", "guess", "final"), "codewords turn"
        )
        g = host.state["game"]  # type: ignore[index]
        if g["phase"] == "final":
            break
        team = g["turn"]
        if g["phase"] == "clue":
            spy = by_id[g["spymasters"][team]]
            await spy.send(t="act", a="clue", word=next(clues), count=rng.randint(0, 3))
            await host.until(
                lambda s, team=team: (
                    (s.get("game") or {}).get("phase") != "clue" or s["game"]["turn"] != team
                ),
                "clue in",
            )
            continue
        guesser = next(b for b in bots if g["teams"][b.pid] == team and b.pid != g["spymasters"][team])
        hidden = [i for i, c in enumerate(g["board"]) if not c["revealed"]]
        n = sum(c["revealed"] for c in g["board"])
        await guesser.send(t="act", a="reveal", card=rng.choice(hidden))
        await host.until(
            lambda s, n=n: sum(c["revealed"] for c in (s["game"] or {}).get("board", [])) > n, "reveal"
        )
    await all_until(bots, game_is("codewords", "final"), "codewords final")
    final = host.state["game"]  # type: ignore[index]
    key = [c["color"] for c in final["board"]]
    check(
        None not in key and key.count("assassin") == 1, "codewords: the final board must show the whole key"
    )
    spies = set(final["spymasters"].values())
    for b in bots:
        for raw in b.raw[start[b.pid] :]:
            gg = json.loads(raw).get("game") or {}
            if gg.get("game") != "codewords" or gg.get("phase") == "final":
                continue
            for i, c in enumerate(gg["board"]):
                if c["revealed"]:
                    check(c["color"] == key[i], "codewords: a revealed colour changed")
                elif b.pid in spies:
                    check(c["color"] == key[i], f"{b.name} (spymaster) was shown a wrong key")
                else:
                    check(c["color"] is None, f"{b.name} (guesser) saw a face-down colour")


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
        games = [
            "frenemy",
            "alibi",
            "price",
            "telepathy",
            "mural",
            "blackjack",
            "crossword",
            "dice",
            "split",
            "chicken",
            "wits",
            "codes",
            "roulette",
            "lonely",
            "boxes",
            "codewords",
            "truthdare",
            "wordrace",
            "lastcard",
            "ludo",
            "chess",
            "drawguess",
            "telephone",
            "tycoon",
        ]
        if len(bots) >= 3:
            games.insert(6, "blackjack-tournament")
        games += ["bomb", "reflex"]
        if len(bots) >= 4:
            games.append("mafia")
            games.append("crossword-teams")
            games += [
                "lastcard-pairs",
                "truthdare-pairs",
                "chess-pairs",
                "drawguess-pairs",
                "telephone-pairs",
                "tycoon-pairs",
            ]  # the Teams switch
        if len(bots) == 4:
            games.append("ludo-pairs")  # Ludo teams are exactly 2 v 2
        for name in games:
            if only and name not in only and name.split("-")[0] not in only:
                continue
            game = name.split("-")[0]
            for b in bots:
                b.errors.clear()  # each game is judged on its own errors
            before = totals(host)
            start = {b.pid: len(b.raw) for b in bots}
            planted: dict[str, set[int]] = {}
            if name == "blackjack-tournament":
                await host.send(t="start", game=game, options={"mode": "tournament"})
            elif name == "crossword-teams":
                await host.send(t="start", game=game, options={"mode": "teams"})
            elif name.endswith("-pairs"):
                await host.send(t="start", game=game, teams=True)
            else:
                await host.send(t="start", game=game)
            # Every game opens with a "how to play" screen; it starts once every player taps Ready.
            await all_until(bots, lambda s: s["room"]["phase"] == "intro", f"{game} intro")
            check(bool(host.state["intro"]["how_to"]), f"{game}: the intro has no rules")  # type: ignore[index]
            for b in bots:
                await b.send(t="ready")
            await all_until(
                bots, lambda s: s["room"]["phase"] == "game", f"{game} starts after everyone is ready"
            )
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
            elif game == "split":
                await play_split(host, bots, rng)
            elif game == "chicken":
                await play_chicken(host, bots, rng)
            elif game == "wits":
                await play_wits(host, bots, rng)
            elif game == "codes":
                await play_codes(host, bots, rng)
            elif game == "roulette":
                await play_roulette(host, bots, rng)
            elif game == "lonely":
                await play_lonely(host, bots, rng)
            elif game == "boxes":
                await play_boxes(host, bots, rng)
            elif game == "codewords":
                await play_codewords(host, bots, rng)
            elif game == "truthdare":
                await play_truthdare(host, bots, rng)
            elif game == "wordrace":
                await play_wordrace(host, bots, rng)
            elif game == "lastcard":
                await play_lastcard(host, bots, rng)
            elif game == "ludo":
                await play_ludo(host, bots, rng)
            elif game == "chess":
                await play_chess(host, bots, rng)
            elif game == "drawguess":
                await play_drawguess(host, bots, rng)
            elif game == "telephone":
                await play_telephone(host, bots, rng)
            elif game == "tycoon":
                await play_tycoon(host, bots, rng)
            elif game == "mafia":
                await play_mafia(host, bots, rng)
            elif game == "bomb":
                await play_bomb(host, bots, rng)
            elif game == "reflex":
                await play_reflex(host, bots, rng)
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
            elif game == "roulette":
                chips = host.state["game"]["chips"]  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(
                    got == {pid: chips[pid] - 1000 for pid in got}, f"roulette: scores {got} != stacks - 1000"
                )
            elif game == "lastcard":
                g = host.state["game"]  # type: ignore[index]
                want = lastcard_scores(g, [b.pid for b in bots])
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"lastcard: scores {got} != hand totals {want}")
                check(
                    sum(h["points"] for h in g["history"]) == sum(want.values()),
                    "lastcard: history vs scores",
                )
            elif game == "chess":
                want = chess_scores(host.state["game"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"chess: scores {got} != the result's {want}")
            elif game == "ludo":
                want = ludo_scores(host.state["game"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"ludo: scores {got} != the colours' points {want}")
                check(
                    sum(1 for p in want.values() if p >= 500) >= 1,
                    "ludo: nobody got the win bonus",
                )
            elif game == "tycoon":
                want = tycoon_scores(host.state["game"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"tycoon: scores {got} != net worth {want}")
            elif game in ("mafia", "bomb", "reflex"):
                want = host.state["game"]["scores"]  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"{game}: scoreboard {got} != the game's {want}")
            elif game == "telephone":
                want = telephone_points(host.state["game"]["books"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"telephone: scores {got} != the likes' points {want}")
            elif game == "drawguess":
                want = drawguess_points(host.state["game"]["history"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"drawguess: scores {got} != the turns' points {want}")
            elif game == "wordrace":
                want = wordrace_points(host.state["game"]["history"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"wordrace: scores {got} != the rounds' points {want}")
            elif game == "truthdare":
                want = truthdare_points(host.state["game"]["history"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"truthdare: scores {got} != payouts {want}")
            elif game == "lonely":
                want = lonely_points(host.state["game"]["history"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"lonely: scores {got} != pots won {want}")
            elif game == "codewords":
                g = host.state["game"]  # type: ignore[index]
                want = {pid: 300 if team == g["winner"] else 0 for pid, team in g["teams"].items()}
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"codewords: scores {got} != the winning team's {want}")
            elif game == "boxes":
                want = boxes_points(host.state["game"]["boxes"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"boxes: scores {got} != value minus price {want}")
            elif game == "codes":
                g = host.state["game"]  # type: ignore[index]
                want = codes_points(g["cracked"], [b.pid for b in bots], g["hint_counts"])
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"codes: scores {got} != crack order {want}")
            elif game == "wits":
                g = host.state["game"]  # type: ignore[index]
                want = wits_points(g["history"], [b.pid for b in bots])
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"wits: scores {got} != revealed gains {want}")
                for h in g["history"]:  # gains follow the rules from the revealed answers and bets
                    under = sorted(v for v in h["answers"].values() if v <= h["answer"])
                    check((h["slot"] == 0) == (not under), "wits: wrong winning slot")
            elif game == "chicken":
                want = chicken_points(host.state["game"]["history"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"chicken: scores {got} != banked values {want}")
            elif game == "split":
                want = split_points(host.state["game"]["history"], [b.pid for b in bots])  # type: ignore[index]
                got = {pid: after[pid] - before[pid] for pid in after}
                check(got == want, f"split: scores {got} != payoffs from the revealed choices {want}")
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
                bad = [e for e in b.errors if e not in EXPECTED_ERRORS | EXPECTED_BY_GAME.get(game, set())]
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
