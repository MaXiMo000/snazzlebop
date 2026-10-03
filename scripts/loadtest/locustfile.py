"""Abuse suite: proves Snazzlebop's per-IP and per-socket limits hold against a running server.

    scripts/loadtest/run.sh            # builds the app + this image, runs it on a private Docker network

Scenarios run in order from ONE client IP (the order matters: guessing codes puts the IP in the
penalty box, so it goes last). Each one is reported to Locust as an "ABUSE" request: pass = the
server defended itself the way SECURITY.md says it does. Locust exits non-zero if any fail.

  1 room_of_8         a legit room: 8 sockets connect, play a Price round, all see the reveal
  2 socket_cap        12 sockets from one IP are accepted, the 13th is refused
  3 message_flood     50 msg/s on one socket is closed with 4008 (slow down)
  4 oversized_frames  a 3 KB frame (app limit 2 KB) and a 20 KB frame (uvicorn 16 KB) close with 1009
  5 slow_reader       a client that never reads is dropped while the room keeps playing
  6 create_flood      a burst of POST /api/rooms gets 429 + Retry-After
  7 code_guessing     wrong codes get 404 then 429, and the guesser's sockets are refused

Run it against a container on the same Docker network, not through Docker Desktop's port proxy:
the proxy buffers on the client's behalf and would hide the slow-reader backpressure.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import socket
import time
from collections.abc import Callable
from typing import Any

import gevent
import requests
import websocket
from locust import User, events, task
from locust.exception import StopUser

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"


class Fail(AssertionError):
    pass


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)


class Suite:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.ws_base = self.base.replace("http", "ws", 1)
        self.http = requests.Session()
        self.http.headers["Origin"] = self.base
        self.code = ""
        self.seats: list[tuple[str, str]] = []  # (player_id, token); seat 0 is the host

    # -- plumbing -----------------------------------------------------------------------------------
    def post(self, path: str, name: str) -> requests.Response:
        return self.http.post(self.base + path, json={"name": name}, timeout=10)

    def connect(self, rcvbuf: int | None = None) -> websocket.WebSocket:
        opts = ((socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf),) if rcvbuf else ()
        return websocket.create_connection(
            f"{self.ws_base}/ws/{self.code}", origin=self.base, timeout=10, sockopt=opts
        )

    def seat(self, i: int, rcvbuf: int | None = None) -> websocket.WebSocket:
        ws = self.connect(rcvbuf)
        ws.send(json.dumps({"t": "auth", "token": self.seats[i][1]}))
        return ws

    @staticmethod
    def state(ws: websocket.WebSocket, pred: Callable[[dict[str, Any]], bool] = lambda s: True) -> dict:
        while True:
            msg = json.loads(ws.recv())
            if msg.get("t") == "state" and pred(msg):
                return msg

    @staticmethod
    def close_code(ws: websocket.WebSocket, within: float) -> int:
        """Read until the server closes; return its close code (1006 = no close frame)."""
        ws.settimeout(within)
        try:
            while True:
                op, data = ws.recv_data(control_frame=True)
                if op == websocket.ABNF.OPCODE_CLOSE:
                    return int.from_bytes(data[:2], "big") if len(data) >= 2 else 1005
        except websocket.WebSocketTimeoutException:
            raise Fail(f"server did not close the socket within {within}s") from None
        except (websocket.WebSocketConnectionClosedException, OSError):
            return 1006

    # -- scenarios ----------------------------------------------------------------------------------
    def room_of_8(self) -> str:
        r = self.post("/api/rooms", "Host")
        expect(r.status_code == 201, f"create room: {r.status_code}")
        self.code = r.json()["code"]
        self.seats = [(r.json()["player_id"], r.json()["token"])]
        for i in range(7):
            r = self.post(f"/api/rooms/{self.code}/join", f"P{i + 1}")
            expect(r.status_code == 200, f"join {i + 1}: {r.status_code}")
            self.seats.append((r.json()["player_id"], r.json()["token"]))
        socks = [self.seat(i) for i in range(8)]
        for ws in socks:
            self.state(ws, lambda s: sum(p["connected"] for p in s["players"]) == 8)
        socks[0].send(json.dumps({"t": "start", "game": "price"}))
        # Every game opens with a "how to play" screen: the host starts it straight away.
        self.state(socks[0], lambda s: s["room"]["phase"] == "intro")
        socks[0].send(json.dumps({"t": "skip"}))
        for i, ws in enumerate(socks):
            self.state(ws, lambda s: (s.get("game") or {}).get("phase") == "guess")
            ws.send(json.dumps({"t": "act", "a": "guess", "amount": 100 + i}))
        for ws in socks:
            self.state(ws, lambda s: (s.get("game") or {}).get("phase") == "reveal")
        socks[0].send(json.dumps({"t": "lobby"}))
        for ws in socks:
            ws.close()
        gevent.sleep(1)
        return "8/8 sockets connected, played a round and saw the reveal"

    def socket_cap(self) -> str:
        held = []
        try:
            for _ in range(12):
                held.append(self.connect())  # unauthenticated still counts against the IP cap
            try:
                extra = self.connect()
            except websocket.WebSocketBadStatusException as exc:
                return f"12 sockets accepted; 13th refused at handshake (HTTP {exc.status_code})"
            extra.close()
            raise Fail("13th socket from one IP was accepted")
        finally:
            for ws in held:
                ws.close()
            gevent.sleep(1)

    def message_flood(self) -> str:
        ws = self.seat(1)
        self.state(ws)
        sent = 0
        try:
            for _ in range(100):
                ws.send(json.dumps({"t": "ping"}))
                sent += 1
                gevent.sleep(0.02)  # 50 msg/s
        except (websocket.WebSocketConnectionClosedException, OSError):
            pass
        code = self.close_code(ws, 5)
        expect(code == 4008, f"flooding socket closed with {code}, expected 4008")
        return f"sent {sent} msgs at ~50/s; server closed the socket with 4008"

    def oversized_frames(self) -> str:
        out = []
        for seat, size in ((2, 3_000), (3, 20_000)):
            ws = self.seat(seat)
            self.state(ws)
            t0 = time.perf_counter()
            with contextlib.suppress(websocket.WebSocketConnectionClosedException, OSError):
                ws.send("x" * size)
            code = self.close_code(ws, 5)
            took = time.perf_counter() - t0
            if size > 16_384:
                # uvicorn rejects this from the frame header (--ws-max-size) and sends 1009, then
                # closes with the unread payload still queued, so the kernel may answer with a TCP
                # reset that overtakes the close frame: the client then sees 1006. Either way the
                # socket must be gone at once.
                expect(code in (1009, 1006) and took < 2, f"{size} B frame: {code} after {took:.1f}s")
            else:
                expect(code == 1009, f"{size} B frame closed with {code}, expected 1009")
            out.append(f"{size // 1000} KB -> {code} in {took * 1000:.0f} ms")
        return ", ".join(out)

    def slow_reader(self) -> str:
        # Host duty moved when scenario 1's sockets closed: ask the server who hosts now, and make
        # that seat the one generating broadcasts.
        probe = self.seat(0)
        host_pid = self.state(probe)["room"]["host"]
        probe.close()
        host = next(i for i, (pid, _) in enumerate(self.seats) if pid == host_pid)
        others = [i for i in range(len(self.seats)) if i != host]
        readers = [self.seat(i) for i in (host, others[0], others[1])]
        slow_pid = self.seats[others[2]][0]
        slow = self.seat(others[2], rcvbuf=4096)  # authenticates, then never reads a byte
        latest: dict[int, dict] = {}
        received = [0]
        frames = [0, 0, 0]
        deals = [0]  # Alibi deals the readers actually saw
        errors: list[str] = []
        ended: list[str] = []

        def drain(i: int, ws: websocket.WebSocket) -> None:
            try:
                while True:
                    raw = ws.recv()
                    received[0] += len(raw)
                    frames[i] += 1
                    msg = json.loads(raw)
                    if msg.get("t") == "state":
                        latest[i] = msg
                        if i == 1 and (msg.get("game") or {}).get("phase") == "briefing":
                            deals[0] += 1
                    elif msg.get("t") == "error" and len(errors) < 5:
                        errors.append(msg.get("code", "?"))
            except Exception as exc:  # reader ends when its socket closes
                ended.append(f"reader{i}: {type(exc).__name__}")

        for ws in readers:
            ws.settimeout(None)  # readers just drain; they may sit idle between frames
        drains = [gevent.spawn(drain, i, ws) for i, ws in enumerate(readers)]

        def slow_connected() -> bool | None:
            s = latest.get(1)
            if not s:
                return None
            return next(p["connected"] for p in s["players"] if p["id"] == slow_pid)

        t0 = time.perf_counter()
        sent = 0
        try:
            while time.perf_counter() - t0 < 120:
                # Host flips between an Alibi deal (big per-player frames) and the lobby: every
                # message is a broadcast the slow client's buffers have to absorb.
                for msg in ({"t": "start", "game": "alibi"}, {"t": "skip"}, {"t": "lobby"}):
                    readers[0].send(json.dumps(msg))
                    sent += 1
                    gevent.sleep(0.16)  # ~6 msg/s, under the 8/s per-socket limit (skip ends the intro)
                if time.perf_counter() - t0 > 2 and slow_connected() is False:
                    took = time.perf_counter() - t0
                    expect(not ended, f"a reading client was dropped too: {ended}")
                    return (
                        f"dropped after {took:.0f}s while the room kept playing: {sent} host msgs, "
                        f"{deals[0]} deals seen, reader frames {frames}, {received[0] // 1024} KB "
                        f"delivered to readers, host errors {errors}"
                    )
                if int(time.perf_counter() - t0) % 30 == 29:
                    slow.send(json.dumps({"t": "ping"}))  # stay under the 90 s idle timeout
            raise Fail("slow reader was not dropped within 120s")
        finally:
            for ws in (*readers, slow):
                ws.close()
            gevent.killall(drains)
            gevent.sleep(1)

    def create_flood(self) -> str:
        statuses = []
        retry_after = None
        for i in range(20):
            r = self.post("/api/rooms", f"Flood{i}")
            statuses.append(r.status_code)
            if r.status_code == 429:
                retry_after = r.headers.get("retry-after")
        expect(429 in statuses, f"no 429 in a burst of 20 creates: {statuses}")
        expect(retry_after is not None, "429 without Retry-After")
        first = statuses.index(429) + 1
        return f"429 from request #{first} of 20 ({statuses.count(429)} refused), Retry-After {retry_after}s"

    def code_guessing(self) -> str:
        statuses = []
        for _ in range(10):
            guess = "".join(secrets.choice(ALPHABET) for _ in range(5))
            statuses.append(self.post(f"/api/rooms/{guess}/join", "Guesser").status_code)
        expect(429 in statuses, f"guessing never got 429: {statuses}")
        first = statuses.index(429) + 1
        expect(first <= 5, f"429 only after {first} guesses")
        real = self.post(f"/api/rooms/{self.code}/join", "Late").status_code
        expect(real == 429, f"penalised IP could still join a real room ({real})")
        try:
            self.seat(0).close()
            raise Fail("penalised IP could still open a game socket")
        except websocket.WebSocketBadStatusException as exc:
            ws_status = exc.status_code
        return (
            f"guesses: {statuses[:first]}... 429 from guess #{first}; "
            f"real join then {real}; socket refused (HTTP {ws_status})"
        )


SCENARIOS = [
    "room_of_8",
    "socket_cap",
    "message_flood",
    "oversized_frames",
    "slow_reader",
    "create_flood",
    "code_guessing",
]
RESULTS: list[tuple[str, bool, str]] = []


class AbuseSuite(User):
    fixed_count = 1

    @task
    def run_all(self) -> None:
        suite = Suite(self.host)
        only = os.environ.get("ABUSE_ONLY")  # e.g. ABUSE_ONLY=slow_reader while debugging
        for name in SCENARIOS:
            if only and name != "room_of_8" and name not in only.split(","):
                continue
            t0 = time.perf_counter()
            exc: Exception | None = None
            detail = ""
            try:
                detail = getattr(suite, name)()
            except Exception as e:  # any failure (assertion or crash) fails the scenario
                exc = e
                detail = f"{type(e).__name__}: {e}"
            RESULTS.append((name, exc is None, detail))
            events.request.fire(
                request_type="ABUSE",
                name=name,
                response_time=(time.perf_counter() - t0) * 1000,
                response_length=0,
                exception=exc,
                context={},
            )
            if name == "room_of_8" and exc is not None:
                break  # everything after needs the room
        gevent.spawn_later(0.1, self.environment.runner.quit)
        raise StopUser()


@events.quitting.add_listener
def report(environment: Any, **_: Any) -> None:
    print("\n=== Snazzlebop abuse suite ===")
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<17} {detail}")
    only = os.environ.get("ABUSE_ONLY")
    wanted = [n for n in SCENARIOS if not only or n == "room_of_8" or n in only.split(",")]
    missing = [n for n in wanted if n not in {r[0] for r in RESULTS}]
    for name in missing:
        print(f"SKIP  {name}")
    if missing or not all(ok for _, ok, _ in RESULTS):
        environment.process_exit_code = 1
