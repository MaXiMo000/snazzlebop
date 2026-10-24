"""Chat, live reactions and voice/video call passes."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from .. import calls
from ..games import Game
from .models import (
    CALL_GAP,
    CHAT_AUDIENCE_BURST,
    CHAT_GAP,
    CHAT_KEEP,
    CHAT_ROOM_BURST,
    CHAT_SHOWN,
    CLUB_CHAT_OFF,
    KEEP_REACTIONS,
    REACT_GAP,
    REACTIONS,
    ROOM_REACTS_PER_SEC,
    Connection,
    HubError,
    Room,
    clean_chat,
)


class SocialMixin:
    def _drop_from_call(self, room: Room, pid: str) -> None:
        """The host removed someone: take them out of the call too (their pass expires on its own)."""
        if calls.enabled(self.settings):
            call_room = calls.room_name(self.settings, room.code, room.created)
            task = asyncio.get_running_loop().create_task(
                calls.remove_participant(self.settings, call_room, pid)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _react(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        emoji = msg.get("e")
        if emoji not in REACTIONS:
            raise HubError("bad_reaction", "Unknown reaction")
        now = self.clock()
        if now - room.react_last.get(pid, -1e9) < REACT_GAP:
            return False  # tapping faster than that just doesn't count
        room.react_window = [t for t in room.react_window if now - t < 1.0]
        if len(room.react_window) >= ROOM_REACTS_PER_SEC:
            return False
        room.react_last[pid] = now
        room.react_window.append(now)
        who = room.players.get(pid) or room.audience.get(pid)
        room.react_seq += 1
        room.reactions = [
            *room.reactions[-(KEEP_REACTIONS - 1) :],
            {"id": room.react_seq, "e": emoji, "by": who.name if who else "?"},
        ]
        return True

    # -- calls (LiveKit) ------------------------------------------------------------------------------
    @staticmethod
    def _call_allowed(room: Room, pid: str) -> bool:
        """Calls are for signed-in accounts; a TV may watch when the room's host is signed in."""
        return (room.host_id if pid in room.viewers else pid) in room.accounts

    async def _call(self, room: Room, pid: str, conn: Connection) -> None:
        """A pass for the room's voice/video call, sent only to the asking connection."""
        if not calls.enabled(self.settings):
            raise HubError("no_calls", "Calls aren't set up on this server")
        if not self._call_allowed(room, pid):
            raise HubError("sign_in", "Sign in to join the call")
        now = self.clock()
        if now - room.call_last.get(pid, -1e9) < CALL_GAP:
            raise HubError("slow_down", "Joining the call already: give it a moment")
        room.call_last[pid] = now
        who = room.players.get(pid) or room.audience.get(pid)
        tv = pid in room.viewers
        name = "TV" if tv else who.name if who else "?"
        call_room = calls.room_name(self.settings, room.code, room.created)
        token = calls.join_token(self.settings, call_room, pid, name, can_publish=not tv)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                conn.send_json({"t": "call", "url": self.settings.livekit_url, "token": token, "tv": tv}), 5
            )

    # -- chat -----------------------------------------------------------------------------------------
    @staticmethod
    def _chat_game(room: Room) -> Game | None:
        return room.game if room.game is not None and room.phase in ("game", "results") else None

    def _chat(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        to = msg.get("to", "all")
        if to not in ("all", "team"):
            raise HubError("bad_message", "Unknown chat channel")
        if not room.club_chat:
            raise HubError("muted", CLUB_CHAT_OFF)
        text = clean_chat(msg.get("text"))
        game = self._chat_game(room)
        seated = pid in room.players
        if game is not None and seated and pid in game.round_scores:
            if game.chat_muted(pid):
                raise HubError("muted", game.CHAT_MUTED_NOTE)
            blocked = game.chat_blocked(pid, text)
            if blocked:
                raise HubError("gives_away", blocked)
        team = None
        if to == "team":
            channel = (
                game.chat_team(pid) if game is not None and seated and pid in game.round_scores else None
            )
            if channel is None:
                raise HubError("no_team", "There's no team chat right now")
            team = channel[0]
        now = self.clock()
        if now - room.chat_last.get(pid, -1e9) < CHAT_GAP:
            raise HubError("slow_down", "Slow down a little")
        # The audience has its own budget, so a crowd of watchers can't crowd the players out.
        burst, window = CHAT_ROOM_BURST if seated else CHAT_AUDIENCE_BURST
        recent = [t for t in (room.chat_window if seated else room.audience_chat_window) if now - t < window]
        if len(recent) >= burst:
            raise HubError("slow_down", "The chat is busy: try again in a moment")
        room.chat_last[pid] = now
        recent.append(now)
        if seated:
            room.chat_window = recent
        else:
            room.audience_chat_window = recent
        who = room.players.get(pid) or room.audience.get(pid)
        room.chat_seq += 1
        room.chat = [
            *room.chat[-(CHAT_KEEP - 1) :],
            {"id": room.chat_seq, "by": pid, "name": who.name if who else "?", "text": text, "team": team},
        ]
        return True

    def _chat_view(self, room: Room, pid: str) -> dict[str, Any]:
        """Everyone sees the room's messages; team messages only reach that team's current members."""
        game = self._chat_game(room)
        playing = game is not None and pid in room.players and pid in game.round_scores
        channel = game.chat_team(pid) if game is not None and playing else None
        mine = channel[0] if channel else None
        shown = [m for m in room.chat if m["team"] is None or (mine is not None and m["team"] == mine)]
        return {
            "messages": [
                {
                    "id": m["id"],
                    "by": m["by"],
                    "name": m["name"],
                    "text": m["text"],
                    "team": m["team"] is not None,
                }
                for m in shown[-CHAT_SHOWN * 2 :]
            ],
            "team": channel[1] if channel else None,
            "muted": not room.club_chat or bool(game is not None and playing and game.chat_muted(pid)),
            "muted_note": CLUB_CHAT_OFF
            if not room.club_chat
            else (game.CHAT_MUTED_NOTE if game is not None else ""),
            "can_send": pid not in room.viewers,
        }
