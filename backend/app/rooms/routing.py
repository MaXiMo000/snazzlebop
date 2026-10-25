"""The message router: validates each message and applies it."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from .. import show as showlib
from ..games import REGISTRY, GameError
from ..games.content import THEMES
from .models import (
    ALLOWED_MESSAGE_TYPES,
    AUDIENCE_MESSAGE_TYPES,
    AVATAR_FACES,
    AVATAR_TONES,
    CALL_GAP,
    KICKED,
    Connection,
    HubError,
    Room,
    clean_name,
)


class RoutingMixin:
    # -- message routing ----------------------------------------------------
    async def handle_message(self, room: Room, pid: str, conn: Connection, msg: Any) -> None:
        if not isinstance(msg, dict) or msg.get("t") not in ALLOWED_MESSAGE_TYPES:
            return await self.send_error(conn, "bad_message", "Unknown message")
        kind = msg["t"]
        if kind == "ping":
            # The reply lets a phone waking from sleep tell a live socket from a dead one.
            # A TV's keep-alive pings don't keep a room alive.
            if pid not in room.viewers:
                room.last_active = self.clock()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(conn.send_json({"t": "pong"}), 5)
            return
        if pid in room.viewers:
            # TV screens only watch: no actions.
            if kind == "inksync":
                return self._ink_sync(room, pid, conn, msg)
            if kind == "call":
                return await self._call(room, pid, conn)
            return await self.send_error(conn, "read_only", "TV mode is read-only")
        if pid in room.audience and kind not in AUDIENCE_MESSAGE_TYPES:
            return await self.send_error(conn, "audience_only", "The audience can react and predict")
        room.last_active = self.clock()
        try:
            if kind == "inksync":
                return self._ink_sync(room, pid, conn, msg)
            if kind == "call":
                return await self._call(room, pid, conn)
            if kind == "ink":
                return await self._ink(room, pid, conn, msg)
            if kind == "boost":
                await self._use_boost(room, pid, msg)
                return await self.broadcast(room)
            async with room.lock:
                changed = self._apply(room, pid, kind, msg)
            if changed:
                await self.broadcast(room)
        except (GameError, HubError) as exc:
            await self.send_error(conn, exc.code, exc.message)

    def _apply(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        is_host = pid == room.host_id
        if kind == "react":
            return self._react(room, pid, msg)
        if kind == "chat":
            return self._chat(room, pid, msg)
        if kind == "avatar":
            face, tone = msg.get("face"), msg.get("tone")
            if (
                type(face) is not int
                or type(tone) is not int
                or not (0 <= face < AVATAR_FACES and 0 <= tone < AVATAR_TONES)
            ):
                raise HubError("bad_message", "Unknown message")
            if room.faces.get(pid) == [face, tone]:
                return False
            room.faces[pid] = [face, tone]
            return True
        if kind == "hush":
            if not is_host:
                raise HubError("not_host", "Only the host can mute everyone", 403)
            now = self.clock()
            if now - room.call_last.get("hush", -1e9) < CALL_GAP:
                raise HubError("slow_down", "Everyone was just muted")
            room.call_last["hush"] = now
            room.call_hush += 1
            return True
        if kind == "predict":
            if pid not in room.audience:
                raise HubError("audience_only", "Only the audience predicts")
            if not self._predict_open(room) or room.game is None:
                raise HubError("predict_closed", "Predictions are closed for this game")
            target = msg.get("target")
            if not isinstance(target, str) or target not in room.game.player_ids:
                raise HubError("bad_target", "Pick a contestant")
            room.predictions[pid] = target
            return True
        if kind == "start":
            if not is_host:
                raise HubError("not_host", "Only the host can start a game", 403)
            if room.phase in ("game", "intro", "market"):
                raise HubError("in_progress", "A game is already running", 409)
            cls = REGISTRY.get(msg.get("game")) if isinstance(msg.get("game"), str) else None
            if cls is None:
                raise HubError("bad_game", "Unknown game")
            if room.club_games and cls.game_id not in room.club_games:
                raise HubError("club_game", "This club doesn't play that one")
            self._check_battle(room, cls.game_id)
            options = self._options(cls, msg.get("options"))
            want_teams, ranked = msg.get("teams", False), msg.get("ranked", False)
            if not isinstance(want_teams, bool) or not isinstance(ranked, bool):
                raise HubError("bad_message", "Unknown message")
            if ranked:
                if want_teams:
                    raise HubError("ranked_teams", "Ranked games are played without the Teams switch")
                self._check_ranked(room, cls.game_id)
                options = {}  # ranked games use the standard settings, the same for everyone
            teams = self._split_teams(room, cls) if want_teams else {}
            # raises (too few players, a team rule) before anything changes
            self._make_game(room, cls, options=options, teams=teams)
            room.show = None  # a one-off game outside any show
            self._open_intro(room, cls.game_id, options, teams=teams, ranked=ranked)
            return True
        if kind == "shuffle":
            if not is_host:
                raise HubError("not_host", "Only the host can shuffle the teams", 403)
            if room.phase != "intro" or not room.intro.get("teams"):
                raise HubError("no_teams", "Teams are shuffled before a team game starts")
            cls = REGISTRY[room.intro["game"]]
            room.intro["teams"] = self._split_teams(room, cls)
            room.ready = set()
            return True
        if kind == "ready":
            return self._ready(room, pid, msg)
        if kind == "show":
            if not is_host:
                raise HubError("not_host", "Only the host can start a show", 403)
            if room.phase in ("game", "intro", "market"):
                raise HubError("in_progress", "A game is already running", 409)
            raw = msg.get("games")
            if (
                not isinstance(raw, list)
                or not showlib.MIN_GAMES <= len(raw) <= showlib.MAX_GAMES
                or any(not isinstance(g, str) or g not in REGISTRY or not REGISTRY[g].SHOW for g in raw)
                or len(set(raw)) != len(raw)
            ):
                raise HubError("bad_show", f"Pick {showlib.MIN_GAMES}-{showlib.MAX_GAMES} different games")
            if room.club_games and set(raw) - set(room.club_games):
                raise HubError("club_game", "This club doesn't play some of those")
            jackpot = msg.get("jackpot", True)
            market = msg.get("market", False)
            if not isinstance(jackpot, bool) or not isinstance(market, bool):
                raise HubError("bad_message", "Unknown message")
            self._start_show(room, list(raw), jackpot, market)
            return True
        if kind == "rematch":
            if not is_host:
                raise HubError("not_host", "Only the host can start a rematch", 403)
            if room.phase != "finale" or not room.last_show:
                raise HubError("no_show", "Rematches start from a show's finale")
            ls = room.last_show
            self._start_show(room, list(ls["games"]), ls["jackpot"], ls["market"])
            return True
        if kind == "card":
            return self._play_card(room, pid, msg)
        if kind == "mvp":
            if pid not in room.audience:
                raise HubError("audience_only", "Only the audience votes for MVP")
            if not self._mvp_open(room) or room.game is None:
                raise HubError("mvp_closed", "MVP voting is closed")
            target = msg.get("target")
            if not isinstance(target, str) or target not in room.game.player_ids:
                raise HubError("bad_target", "Pick a contestant")
            room.mvp_votes[pid] = target
            return True
        if kind == "trade":
            market = room.show.market if room.show else None
            trader_ok = pid in room.players or pid in room.audience
            if not trader_ok or market is None or room.phase != "market":
                raise HubError("market_closed", "The market is closed")
            target, qty = msg.get("target"), msg.get("qty")
            if not isinstance(target, str) or target not in room.players:
                raise HubError("bad_trade", "Pick a player to trade")
            if isinstance(qty, bool) or not isinstance(qty, int):
                raise HubError("bad_trade", "Trade a whole number of shares")
            market.seat(pid, listed=pid in room.players)
            market.seat(target)
            try:
                market.trade(pid, target, qty)
            except ValueError as exc:
                raise HubError("bad_trade", str(exc)) from None
            return True
        if kind == "next":
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            s = room.show
            if s is None or s.finished or room.phase != "results":
                raise HubError("no_show", "No show segment to start")
            if msg.get("skip") is True and s.next_game() not in (None, "jackpot"):
                s.started += 1  # e.g. not enough players online for that game
            self._start_next(room, s)
            return True
        if kind == "theme":
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            theme = msg.get("theme")
            if not isinstance(theme, str) or (theme and theme not in THEMES):
                raise HubError("bad_theme", "Unknown show pack")
            room.theme = theme
            return True
        if kind == "act":
            if room.game is None or room.phase != "game":
                raise HubError("no_game", "No game is running")
            action = {k: v for k, v in msg.items() if k != "t"}
            room.game.handle(pid, action)
            self._maybe_finish(room)
            return True
        if kind == "skip":
            if not is_host:
                raise HubError("not_host", "Only the host can skip", 403)
            if room.phase == "market":  # the host rings the closing bell early
                self._close_market(room)
                return True
            if room.phase == "intro":  # the host starts the game now
                self._close_intro(room)
                return True
            if room.game is None or room.phase != "game":
                raise HubError("no_game", "No game is running")
            seen = msg.get("stage")
            if seen is not None:
                if not isinstance(seen, str) or len(seen) > 32:
                    raise HubError("bad_message", "Unknown message")
                if seen != room.game.stage:
                    return False  # the wait the host meant to skip already ended on its own
            if not room.game.skip():
                raise HubError("no_skip", "This part runs on its own clock: no skipping it")
            self._maybe_finish(room)
            return True
        if kind == "lobby":
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            if room.phase == "finale":  # keep the final standings on the lobby screen
                room.last_standings = sorted(
                    (
                        {"id": p.id, "name": p.name, "total": room.total_scores.get(p.id, 0)}
                        for p in room.players.values()
                    ),
                    key=lambda r: -r["total"],
                )
            room.intro, room.ready = {}, set()
            room.game, room.phase, room.show = None, "lobby", None
            room.highlights, room.quip, room.predictions = [], "", {}
            room.rivals, room.rival_news, room.card_news, room.mvp_votes = [], [], [], {}
            return True
        if kind in ("crown", "forfeit", "wheel"):
            if pid not in room.players:
                raise HubError("players_only", "Only contestants can do that")
            return self._night(room, pid, kind, msg)
        if kind in ("kick", "lock", "title"):
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            return self._host_tool(room, pid, kind, msg)
        if kind == "leave":
            player = room.players.get(pid)
            if player and room.phase == "lobby" and pid != room.host_id:
                del room.players[pid]
                room.total_scores.pop(pid, None)
                room.faces.pop(pid, None)
                conn = room.conns.pop(pid, None)
                if conn is not None:
                    asyncio.get_running_loop().create_task(conn.close(1000))
            return True
        return False

    def _host_tool(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        if kind == "title":
            raw = msg.get("title")
            room.title = "" if raw == "" else clean_name(raw, max_len=32)
            return True
        if kind == "lock":
            if not isinstance(msg.get("locked"), bool):
                raise HubError("bad_message", "Unknown message")
            room.locked = msg["locked"]
            return True
        target = msg.get("target")
        if isinstance(target, str) and target in room.audience:  # the crowd can go at any time
            watcher = room.audience.pop(target)
            room.predictions.pop(target, None)
            self._drop_from_call(room, target)
            if watcher.conn is not None:
                asyncio.get_running_loop().create_task(watcher.conn.close(KICKED))
            return True
        if not isinstance(target, str) or target not in room.players or target == pid:
            raise HubError("bad_target", "Pick another player")
        if room.phase == "game":
            raise HubError("in_progress", "Remove players between games")
        del room.players[target]
        room.total_scores.pop(target, None)
        room.faces.pop(target, None)
        self._drop_from_call(room, target)
        conn = room.conns.pop(target, None)
        if conn is not None:
            asyncio.get_running_loop().create_task(conn.close(KICKED))
        return True
