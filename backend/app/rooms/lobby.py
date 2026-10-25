"""Creating and joining rooms, seats, TV and audience passes, connections, host handover."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from typing import Any

from .. import prank
from ..games import Player
from ..security import sign_token
from .models import (
    FORFEIT_MAX,
    HOST_GRACE,
    MAX_AUDIENCE,
    MAX_FORFEITS,
    MAX_TV_PER_ROOM,
    ROOM_ALPHABET,
    ROOM_CODE_RE,
    Connection,
    HubError,
    Room,
    Watcher,
    clean_name,
)


class LobbyMixin:
    # -- rooms --------------------------------------------------------------
    def _new_code(self) -> str:
        for _ in range(50):
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(self.settings.room_code_length))
            if code not in self.rooms:
                return code
        raise HubError("busy", "Try again in a moment", 503)

    def _issue(self, room: Room, player: Player) -> str:
        return sign_token(self.settings.secret_key, player.id, room.code, self.settings.token_ttl_seconds)

    def create_room(
        self,
        name: str,
        user_id: int | None = None,
        circle: dict[str, Any] | None = None,
        club_id: int | None = None,
        club_rules: dict[str, Any] | None = None,
        club_muted: dict[int, float] | None = None,
    ) -> tuple[Room, Player, str]:
        self.cleanup()
        if len(self.rooms) >= self.settings.max_rooms:
            raise HubError("busy", "The party house is full right now. Try again soon.", 503)
        name = clean_name(name)
        room = Room(code=self._new_code(), created=self.clock(), last_active=self.clock(), club_id=club_id)
        room.club_muted = dict(club_muted or {})
        if club_rules:
            room.club_games, room.club_chat = list(club_rules["games"]), bool(club_rules["chat"])
        player = Player(id=secrets.token_urlsafe(6), name=name, connected=False)
        room.players[player.id] = player
        room.host_id = player.id
        room.total_scores[player.id] = 0
        if user_id is not None:
            room.accounts[player.id] = user_id
        if circle:  # what this host's last night left behind
            room.belt = str(circle.get("belt") or "")[:32]
            room.forfeits = [str(x)[:FORFEIT_MAX] for x in (circle.get("forfeits") or [])][:MAX_FORFEITS]
        self.rooms[room.code] = room
        self._scare(room, player.id, name)
        self._persist(room)
        return room, player, self._issue(room, player)

    def club_rooms(self, club_id: int) -> list[dict[str, Any]]:
        """A club's live rooms, for its members to walk into: code, host, how many, what's on."""
        out = []
        for room in self.rooms.values():
            if room.club_id != club_id or not room.connected_players():
                continue
            host = room.players.get(room.host_id)
            out.append(
                {
                    "code": room.code,
                    "host": host.name if host else "",
                    "players": len(room.connected_players()),
                    "phase": room.phase,
                    "game": room.game.title if room.game is not None else None,
                    "open": not room.locked and room.phase == "lobby",
                    "battle": bool(room.battle),
                }
            )
        return sorted(out, key=lambda r: (not r["open"], -r["players"]))

    def set_battle(self, room: Room, battle_id: int, game: str, kind: str, accounts: list[int]) -> None:
        """This room's first game is a battle (battles.py): that game, and for a duel those two players."""
        room.battle = {"id": battle_id, "game": game, "kind": kind, "accounts": list(accounts)}
        self._persist(room)

    def get(self, code: str) -> Room | None:
        if not isinstance(code, str) or not ROOM_CODE_RE.match(code):
            return None
        return self.rooms.get(code)

    def join_room(self, code: str, name: str, user_id: int | None = None) -> tuple[Room, Player, str]:
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            raise HubError("room_not_found", "No room with that code", 404)
        name = clean_name(name)
        if room.locked:
            raise HubError("room_locked", "The host has locked this room", 409)
        if room.phase == "game":
            raise HubError("in_progress", "That game has already started", 409)
        if len(room.players) >= self.settings.max_players_per_room:
            raise HubError("room_full", "That room is full", 409)
        self._name_free(room, name)
        player = Player(id=secrets.token_urlsafe(6), name=name, connected=False)
        room.players[player.id] = player
        room.total_scores[player.id] = 0
        if user_id is not None:
            room.accounts[player.id] = user_id
        room.last_active = self.clock()
        self._scare(room, player.id, name)
        self._persist(room)
        return room, player, self._issue(room, player)

    def _scare(self, room: Room, pid: str, name: str | None = None) -> None:
        """Queue a jump scare for this person if their name is on the (private) list. With a name, it's
        their arrival; without, it's a score screen for someone already matched."""
        if not self.prank_targets:
            return
        if name is not None:
            if not prank.matches(name, self.prank_targets):
                return
        elif pid not in room.scares:
            return
        room.scares[pid] = room.scares.get(pid, 0) + 1
        if name is not None:  # and a walk-on the whole room sees
            room.entrance = {"id": room.entrance.get("id", 0) + 1, "pid": pid, "name": name}

    def _scare_everyone_matched(self, room: Room) -> None:
        for pid in list(room.scares):
            if pid in room.players or pid in room.audience:
                self._scare(room, pid)

    @staticmethod
    def _name_free(room: Room, name: str) -> None:
        taken = [*(p.name for p in room.players.values()), *(w.name for w in room.audience.values())]
        if any(n.casefold() == name.casefold() for n in taken):
            raise HubError("name_taken", "Someone already has that name", 409)

    def join_audience(self, code: str, name: str, user_id: int | None = None) -> tuple[Room, Watcher, str]:
        """A named seat in the crowd: works when the room is full or mid-game, not when it's locked."""
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            raise HubError("room_not_found", "No room with that code", 404)
        name = clean_name(name)
        if room.locked:
            raise HubError("room_locked", "The host has locked this room", 409)
        if len(room.audience) >= MAX_AUDIENCE:
            raise HubError("audience_full", "The audience is full", 409)
        self._name_free(room, name)
        watcher = Watcher(id="au:" + secrets.token_urlsafe(6), name=name)
        room.audience[watcher.id] = watcher
        if user_id is not None:
            room.accounts[watcher.id] = user_id
        room.last_active = self.clock()
        self._scare(room, watcher.id, name)
        self._persist(room)
        token = sign_token(self.settings.secret_key, watcher.id, room.code, self.settings.token_ttl_seconds)
        return room, watcher, token

    def hosting(self, user_ids: set[int]) -> dict[int, str]:
        """Rooms these accounts are hosting right now that a friend could walk into: account -> code."""
        out: dict[int, str] = {}
        for room in self.rooms.values():
            uid = room.accounts.get(room.host_id)
            if (
                uid in user_ids
                and not room.locked
                and room.phase == "lobby"
                and len(room.players) < self.settings.max_players_per_room
                and room.players[room.host_id].connected
            ):
                out[uid] = room.code
        return out

    def playing(self, user_ids: set[int]) -> set[int]:
        """Which of these accounts are in a room right now (connected), for "in a game" presence."""
        out: set[int] = set()
        for room in self.rooms.values():
            for pid, uid in room.accounts.items():
                if uid in user_ids and (p := room.players.get(pid)) is not None and p.connected:
                    out.add(uid)
        return out

    def seated(self, code: str, user_id: int) -> Room | None:
        """The room, if this account has a seat in it (to invite people there)."""
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None or user_id not in {uid for pid, uid in room.accounts.items() if pid in room.players}:
            return None
        return room

    # -- safety ------------------------------------------------------------------------------------------
    def host_account(self, code: str) -> int | None:
        room = self.get(code.upper() if isinstance(code, str) else code)
        return room.accounts.get(room.host_id) if room is not None else None

    def set_hidden(self, user_id: int, others: set[int]) -> None:
        """Who this account must not hear from (and who must not hear from it), in every room it's in."""
        for room in self.rooms.values():
            seated = set(room.accounts.values())
            if user_id in seated:
                room.hidden[user_id] = set(others)
            for uid in seated - {user_id}:  # the other side of each block, for people already here
                if uid in others:
                    room.hidden.setdefault(uid, set()).add(user_id)
                else:
                    room.hidden.get(uid, set()).discard(user_id)

    def club_mute(self, club_id: int, user_id: int, until: float | None) -> None:
        """A moderator's mute (or its end) reaches the club's live rooms at once."""
        for room in self.rooms.values():
            if room.club_id == club_id:
                if until is None:
                    room.club_muted.pop(user_id, None)
                else:
                    room.club_muted[user_id] = until

    def seat_of(self, code: str, pid: str) -> tuple[Room, str, int | None] | None:
        """(room, the name they go by, their account if any) for a player or audience seat."""
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            return None
        who = room.players.get(pid) or room.audience.get(pid)
        return (room, who.name, room.accounts.get(pid)) if who is not None else None

    def said(self, room: Room, pid: str, limit: int = 10) -> list[dict[str, str]]:
        """Their last chat lines in this room: the context a report carries (taken here, never from the
        reporter)."""
        return [{"name": m["name"], "text": m["text"]} for m in room.chat if m["by"] == pid][-limit:]

    def link_account(self, room: Room, pid: str, user_id: int) -> None:
        """A guest who signed in after sitting down: their seat now belongs to their account."""
        if pid in room.accounts or not (pid in room.players or pid in room.audience):
            return
        room.accounts[pid] = user_id
        self._persist(room)

    def issue_tv(self, code: str) -> tuple[Room, str]:
        """A read-only big-screen seat. Same trust as joining: anyone holding the room code."""
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            raise HubError("room_not_found", "No room with that code", 404)
        vid = "tv:" + secrets.token_urlsafe(6)
        room.viewers[vid] = None
        while len(room.viewers) > MAX_TV_PER_ROOM:
            oldest = next(iter(room.viewers))
            conn = room.viewers.pop(oldest)
            if conn is not None:
                asyncio.get_running_loop().create_task(conn.close(1008))
        self._persist(room)
        token = sign_token(self.settings.secret_key, vid, room.code, self.settings.token_ttl_seconds)
        return room, token

    def is_member(self, room: Room, pid: str) -> bool:
        return pid in room.players or pid in room.viewers or pid in room.audience

    def cleanup(self) -> None:
        now = self.clock()
        gone = []
        for code, room in list(self.rooms.items()):
            idle = not room.conns and now - room.last_active > self.settings.room_idle_seconds
            old = now - room.created > self.settings.room_max_age_seconds
            if idle or old:
                del self.rooms[code]
                gone.append(code)
        if gone and self.store is not None and self.store.ready:
            with contextlib.suppress(RuntimeError):  # no running loop (sync tests): nothing was saved
                task = asyncio.get_running_loop().create_task(self.store.delete_snapshots(gone))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    # -- connections --------------------------------------------------------
    async def connect(self, room: Room, pid: str, conn: Connection) -> None:
        if pid in room.viewers:
            previous = room.viewers[pid]
            room.viewers[pid] = conn
            if previous is not None:
                with contextlib.suppress(Exception):
                    await previous.close(1000)
            task = self._post(room, pid, conn, self.view_for(room, pid))  # only the screen needs a frame
            if task is not None:
                await asyncio.wait([task], timeout=0.25)
            return
        if pid in room.audience:
            watcher = room.audience[pid]
            previous_conn, watcher.conn = watcher.conn, conn
            room.last_active = self.clock()
            if previous_conn is not None:
                with contextlib.suppress(Exception):
                    await previous_conn.close(1000)
            await self.broadcast(room)  # players see the crowd grow
            return
        async with room.lock:
            previous = room.conns.get(pid)
            room.conns[pid] = conn
            room.players[pid].connected = True
            if pid == room.host_id:
                room.host_away = None
            room.last_active = self.clock()
        if previous is not None:
            with contextlib.suppress(Exception):  # already gone
                await previous.close(1000)
        await self.broadcast(room)

    async def disconnect(self, room: Room, pid: str, conn: Connection) -> None:
        if pid in room.viewers or pid.startswith("tv:"):
            if room.viewers.get(pid) is conn:
                room.viewers[pid] = None
            return
        if pid.startswith("au:"):
            watcher = room.audience.get(pid)
            if watcher is not None and watcher.conn is conn:
                watcher.conn = None
                await self.broadcast(room)
            return
        async with room.lock:
            if room.conns.get(pid) is not conn:
                return  # superseded by a newer connection
            room.conns.pop(pid, None)
            player = room.players.get(pid)
            if player:
                player.connected = False
            if room.host_id == pid:
                room.host_away = self.clock()  # the ticker hands the room on only if they stay away
            room.last_active = self.clock()
        await self.broadcast(room)

    # -- timers -------------------------------------------------------------
    def _hand_over(self, room: Room) -> bool:
        """The host has been gone longer than HOST_GRACE: the first connected player takes over."""
        host = room.players.get(room.host_id)
        if host is not None and host.connected:
            room.host_away = None
            return False
        if room.host_away is None:  # e.g. a room restored after a restart, host not back yet
            room.host_away = self.clock()
        if self.clock() - room.host_away < HOST_GRACE:
            return False
        heir = next((p.id for p in room.players.values() if p.connected), None)
        if heir is None:
            return False  # nobody here to take over: keep waiting
        room.host_id = heir
        room.host_away = None
        return True
