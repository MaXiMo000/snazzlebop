"""Dev tool (not production): a host + 3 bots in one room, so you can join it from a real browser and
watch/test a game at phone width.

Usage (API on :8000 with JUMPSCARE=false, web on :5173):
    backend/.venv/Scripts/python.exe -u docs/handoff/tools/drive.py
It writes the room code to <tmp>/snazzlebop-drive/code.txt. Join http://localhost:5173/r/<CODE> in the
browser, then start a game by writing a command to <tmp>/snazzlebop-drive/cmd.txt:
    "lastcard@9999"            start Last Card, host never skips (natural timers)
    "wordrace:rounds=1@4"      start with an option; host skips every 4 s
    "show@1"                   a show night (lonely + telepathy + jackpot + market)
The command must differ from the previous one to run (change the @pace number to repeat a game).
done.txt holds the last finished command. Bots know Truth or Dare, Word Race (solver), Last Card,
Lowest Lonely Number and Telepathy; extend bot_act for new games.
"""

import asyncio, json, random, sys, pathlib, tempfile, httpx, websockets

BASE = "http://localhost:8000"
REPO = pathlib.Path(__file__).resolve().parents[3]
# Control files live in the temp dir, never in the repo.
HERE = pathlib.Path(tempfile.gettempdir()) / "snazzlebop-drive"
HERE.mkdir(exist_ok=True)
CMD, DONE = HERE / "cmd.txt", HERE / "done.txt"
NAMES = ["No talk", "Leo", "Bartholomew X", "Zara"]


async def seat(code, name):
    r = httpx.post(f"{BASE}/api/rooms/{code}/join", json={"name": name}).json()
    return r


async def client(code, token, on_state):
    ws = await websockets.connect(f"ws://localhost:8000/ws/{code}")
    await ws.send(json.dumps({"t": "auth", "token": token}))

    async def loop():
        async for raw in ws:
            m = json.loads(raw)
            if m.get("t") == "state":
                LATEST[id(ws)] = m
                asyncio.create_task(on_state(ws, m))  # never block reading: act on the latest state

    async def ping():
        while True:
            await asyncio.sleep(20)
            await ws.send(json.dumps({"t": "ping"}))

    asyncio.create_task(ping())
    return ws, asyncio.create_task(loop())


SENT = set()
LATEST: dict[int, dict] = {}
BUSY: dict[int, bool] = {}


async def bot_act(ws, st):
    g = st.get("game") or {}
    key = (id(ws), st["room"]["phase"], st.get("stage"), (st.get("intro") or {}).get("game"), len(((st.get("game") or {}).get("boards") or {}).get(st["you"], [])), json.dumps((g.get("log") or [])[-1:]), g.get("turn"))
    if key in SENT:
        return
    SENT.add(key)
    gid, ph = g.get("game"), g.get("phase")
    me = st["you"]
    try:
        if st["room"]["phase"] == "intro" or (st.get("ready") or {}).get("open"):
            await ws.send(json.dumps({"t": "ready", "stage": (st.get("ready") or {}).get("stage")}))
        if gid == "telepathy" and ph == "pick" and g.get("your_pick") is None:
            await ws.send(json.dumps({"t": "act", "a": "pick", "option": random.randint(0, 2)}))
        if gid == "wordrace" and ph == "play" and not g["you"]["done"]:
            sys.path.insert(0, str(REPO / "backend"))
            from app.games.content import WORD_ANSWERS
            from app.games.wordrace import mark

            rows = g["boards"][me]
            pool = [w for w in WORD_ANSWERS if all(mark(r["word"], w) == r["marks"] for r in rows)]
            await asyncio.sleep(random.uniform(6, 14))
            if pool:
                await ws.send(json.dumps({"t": "act", "a": "guess", "word": random.choice(pool)}))
        if gid == "lastcard" and ph == "play" and g.get("turn") == me:
            await asyncio.sleep(random.uniform(2, 3.5))
            g = (LATEST[id(ws)].get("game") or {})
            if g.get("turn") != me or g.get("phase") != "play" or BUSY.get(id(ws)):
                return
            BUSY[id(ws)] = True
            asyncio.get_running_loop().call_later(1.0, BUSY.pop, id(ws), None)
            you = g["you"]
            if g["pending"] is not None:
                await ws.send(json.dumps({"t": "act", "a": "draw"}))
            else:
                if you["can_last"] and random.random() < 0.6:
                    await ws.send(json.dumps({"t": "act", "a": "last"}))
                    await asyncio.sleep(0.6)
                ok = [c for c in you["hand"] if c["playable"]]
                if ok:
                    c = random.choice(ok)
                    msg = {"t": "act", "a": "play", "card": c["id"]}
                    if c["color"] == "wild":
                        msg["color"] = random.choice(["red", "yellow", "green", "blue"])
                    await ws.send(json.dumps(msg))
                elif you["drawn"] is not None:
                    await ws.send(json.dumps({"t": "act", "a": "pass"}))
                else:
                    await ws.send(json.dumps({"t": "act", "a": "draw"}))
        if gid == "ludo" and ph == "play" and g.get("turn") == me:
            await asyncio.sleep(random.uniform(1.6, 2.6))  # long enough to watch the hops
            g = LATEST[id(ws)].get("game") or {}
            if g.get("turn") != me or g.get("phase") != "play" or BUSY.get(id(ws)):
                return
            BUSY[id(ws)] = True
            asyncio.get_running_loop().call_later(1.0, BUSY.pop, id(ws), None)
            if g["rolled"] is None:
                await ws.send(json.dumps({"t": "act", "a": "roll"}))
            elif g["movable"]:
                await ws.send(json.dumps({"t": "act", "a": "move", "token": random.choice(g["movable"])}))
        if gid == "truthdare":
            await asyncio.sleep(2.5)  # slow enough to watch
            if ph == "choose" and g["target"] == me:
                await ws.send(json.dumps({"t": "act", "a": "choose", "choice": random.choice(["truth", "dare"])}))
            elif ph == "perform" and g["target"] == me:
                await asyncio.sleep(4)
                await ws.send(json.dumps({"t": "act", "a": "done"}))
            elif ph == "vote" and g["target"] != me and g["you_voted"] is None:
                await ws.send(json.dumps({"t": "act", "a": "vote", "like": random.random() < 0.75}))
        if gid == "lonely" and ph == "pick" and g["you"]["pick"] is None:
            await ws.send(json.dumps({"t": "act", "a": "pick", "n": random.randint(1, 6)}))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print("bot_act failed:", repr(exc), flush=True)


async def main():
    r = httpx.post(f"{BASE}/api/rooms", json={"name": NAMES[0]}).json()
    code = r["code"]
    print(code, flush=True)
    (HERE / "code.txt").write_text(code)
    host_state = {}
    last_stage = [None]

    async def host_on(ws, st):
        host_state.update(st)
        await bot_act(ws, st)

    hws, _ = await client(code, r["token"], host_on)
    for n in NAMES[1:]:
        b = await seat(code, n)
        await client(code, b["token"], bot_act)
    seen = ""
    while True:
        await asyncio.sleep(0.5)
        if not CMD.exists():
            continue
        cmd = CMD.read_text().strip()
        if cmd == seen or not cmd:
            continue
        seen = cmd
        cmd0, _, pace = cmd.partition("@")
        pace = float(pace or 1.2)
        gid, _, opt = cmd0.partition(":")
        await hws.send(json.dumps({"t": "lobby"}))
        await asyncio.sleep(0.5)
        if gid == "show":
            await hws.send(json.dumps({"t": "show", "games": ["lonely", "telepathy"], "jackpot": True, "market": True}))
            for _ in range(300):
                await asyncio.sleep(1.5)
                ph = host_state.get("room", {}).get("phase")
                if ph == "finale":
                    break
                if ph == "results":
                    await asyncio.sleep(4)
                    await hws.send(json.dumps({"t": "next"}))
                elif ph == "game":
                    await hws.send(json.dumps({"t": "skip", "stage": host_state.get("stage")}))
                elif ph in ("intro", "market"):
                    await asyncio.sleep(3)
                    await hws.send(json.dumps({"t": "skip"}))
            DONE.write_text(cmd)
            continue
        msg = {"t": "start", "game": gid}
        if opt:
            k, v = opt.split("=")
            msg["options"] = {k: v}
        await hws.send(json.dumps(msg))
        for _ in range(120):
            waited = 0.0
            while waited < pace and host_state.get("room", {}).get("phase") != "results":
                await asyncio.sleep(0.5)
                waited += 0.5
            ph = host_state.get("room", {}).get("phase")
            if ph == "results":
                break
            await hws.send(json.dumps({"t": "skip", "stage": host_state.get("stage")} if ph == "game" else {"t": "skip"}))
        DONE.write_text(cmd)


asyncio.run(main())
