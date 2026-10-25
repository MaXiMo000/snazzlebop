"""A game's life: teams, the intro, starting, Ready votes, finishing, the clock."""

from __future__ import annotations

import asyncio
from typing import Any

from .. import battles as battlelib
from .. import fairplay
from .. import ratings as ratinglib
from .. import show as showlib
from ..games import REGISTRY, Game, GameError, Player
from ..games.catalogue import RANKED, ranked_min
from ..games.jackpot import Jackpot
from .models import (
    TEAM_MIN_PLAYERS,
    HubError,
    Room,
    log,
)


class FlowMixin:
    def _too_quick(self, room: Room) -> bool:
        """The game ended too soon after it began to pay anything (fairplay.py)."""
        return room.game_began >= 0 and fairplay.too_quick(self.clock() - room.game_began)

    @staticmethod
    def _paid_accounts(room: Room) -> dict[str, int]:
        """Seat -> account for the accounts seated when the game began (a room saved before this was
        tracked falls back to the room's accounts)."""
        return room.game_accounts if room.game_began >= 0 else room.accounts

    @staticmethod
    def _all_signed_in(room: Room) -> bool:
        accounts = [room.accounts.get(p.id) for p in room.connected_players()]
        return None not in accounts and len(set(accounts)) == len(accounts)

    def _check_battle(self, room: Room, game_id: str) -> None:
        """A battle room plays its battle first: that game, and (a duel) just the two players in it."""
        b = room.battle
        if not b:
            return
        if game_id != b["game"]:
            raise HubError(
                "battle_game", f"This room's battle is {REGISTRY[b['game']].title}: start that one"
            )
        online = {room.accounts.get(p.id) for p in room.connected_players()}
        if b["kind"] == "duel" and online != set(b["accounts"]):
            raise HubError("battle_players", "A duel starts when both players are here, and only them")
        short = len(online) < battlelib.GROUP_MIN or not self._all_signed_in(room)
        if b["kind"] == "group" and short:
            raise HubError(
                "battle_players",
                f"A group battle needs {battlelib.GROUP_MIN} or more players, each signed in",
            )

    def _check_ranked(self, room: Room, game_id: str) -> None:
        """A ranked game: a ranked kind of game, enough players, every one of them signed in (one seat
        per account). Raises with what's missing."""
        if game_id not in RANKED:
            raise HubError("not_ranked", "That game isn't played ranked")
        online = [p.id for p in room.connected_players()]
        need = ranked_min(game_id) or 2
        if len(online) < need:
            raise HubError("too_few", f"Ranked games need {need} or more players online")
        if not self._all_signed_in(room):
            raise HubError("ranked_guests", "Everyone needs to be signed in, each with their own account")

    def _split_teams(self, room: Room, cls: type[Game]) -> dict[str, int]:
        """Everyone online, shuffled into two teams as even as can be."""
        if not cls.TEAMS:
            raise HubError("no_teams", f"{cls.title} has no team mode")
        online = [p.id for p in room.connected_players()]
        if len(online) < TEAM_MIN_PLAYERS:
            raise HubError("too_few", f"Teams need {TEAM_MIN_PLAYERS} or more players online")
        self.rng.shuffle(online)
        return {pid: i % 2 for i, pid in enumerate(online)}

    def _make_game(self, room: Room, cls: type[Game], **extra: Any) -> Game:
        """Build and start a game for everyone online. Raises (and changes nothing) if it can't start."""
        members = [Player(id=p.id, name=p.name) for p in room.connected_players()]
        game = cls(
            members,
            rng=self.rng,
            clock=self.clock,
            timings=self.timings.get(cls.game_id),
            decks=room.decks,
            theme=room.theme,
            **extra,
        )
        game.start()
        return game

    @staticmethod
    def _options(cls: type[Game], raw: Any) -> dict[str, str]:
        """Only options the game declares, with one of its allowed values."""
        if raw is None:
            return {}
        if not isinstance(raw, dict) or len(raw) > len(cls.OPTIONS):
            raise HubError("bad_options", "Unknown game options")
        for key, value in raw.items():
            if key not in cls.OPTIONS or value not in cls.OPTIONS[key]:
                raise HubError("bad_options", "Unknown game options")
        return dict(raw)

    def _begin(self, room: Room, game: Game) -> None:
        room.game, room.phase = game, "game"
        room.ready, room.ready_stage, room.last_standings = set(), "", []
        room.predictions, room.highlights, room.quip = {}, [], ""
        room.card_news, room.rival_news, room.rivals, room.mvp_votes = [], [], [], {}
        room.game_no += 1
        room.boost_peeks, room.coin_news, room.team_news, room.rating_news = {}, {}, {}, {}
        room.battle_news = {}
        room.game_began = self.clock()
        room.power_news, room.power_private = [], {}
        room.game_accounts = {p: room.accounts[p] for p in game.player_ids if p in room.accounts}
        room.chat = [m for m in room.chat if m["team"] is None]  # new game, new teams: old team talk goes
        s = room.show
        if s is not None:
            s.peeks.clear()
            if game.game_id != "jackpot":
                showlib.deal_cards(s, game.player_ids, self.rng)
                room.rivals = showlib.rivals(room.total_scores, game.player_ids, self.rng)
        if self.on_game_started and game.game_id in REGISTRY:  # top up content in the background
            try:
                self.on_game_started(game.game_id, room.theme)
            except Exception:
                log.exception("on_game_started failed")

    def _open_intro(
        self,
        room: Room,
        game_id: str,
        options: dict[str, str] | None = None,
        slot: str = "",
        teams: dict[str, int] | None = None,
        ranked: bool = False,
    ) -> None:
        """The "how to play" screen. The game is built (and its clocks start) only when it ends."""
        room.intro = {
            "game": game_id,
            "options": dict(options or {}),
            "slot": slot,
            "teams": dict(teams or {}),
            "ranked": ranked,
        }
        room.ready = set()
        room.predictions, room.highlights, room.quip = {}, [], ""
        if self.intro_seconds <= 0:
            self._close_intro(room)
            return
        room.game, room.phase = None, "intro"
        room.intro_until = self.clock() + self.intro_seconds

    def _close_intro(self, room: Room) -> None:
        i, s = room.intro, room.show
        if not i:
            return
        room.intro, room.ready = {}, set()
        teams: dict[str, int] = {}
        try:
            if i.get("ranked"):  # someone may have left, or a guest arrived, during the intro
                self._check_ranked(room, i["game"])
            if i["game"] == "jackpot":
                stakes = {p.id: room.total_scores.get(p.id, 0) for p in room.players.values()}
                game = self._make_game(room, Jackpot, stakes=stakes)
            else:
                teams = i.get("teams") or {}
                game = self._make_game(room, REGISTRY[i["game"]], options=i["options"], teams=teams)
        except (GameError, HubError):
            # Someone left during the intro and the game can't run.
            if s is not None and i["slot"] == "playlist":
                s.started += 1
                room.phase = "results"
                self._start_next(room, s)
            elif s is not None and i["slot"] == "jackpot":
                s.jackpot_played = True
                room.phase = "results"
                self._start_next(room, s)
            else:
                room.game, room.phase = None, "lobby"
            return
        # Only the host's Teams switch makes room teams (Codewords keeps its own red/blue in game.teams).
        room.teams = {p: t for p, t in teams.items() if p in game.round_scores}
        room.ranked = bool(i.get("ranked"))
        self._begin(room, game)
        if s is not None and i["slot"] == "playlist":
            s.started += 1
        elif s is not None and i["slot"] == "jackpot":
            s.jackpot_played = True

    def _ready(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        """Ready votes: on the intro, everyone online starts the game; on a results/briefing screen,
        everyone in the game moves it on. Nobody can be rushed: it takes every single vote."""
        if pid not in room.players:
            raise HubError("players_only", "Only contestants can do that")
        online = {p.id for p in room.connected_players()}
        if room.phase == "intro":
            room.ready.add(pid)
            if online <= room.ready:
                self._close_intro(room)
            return True
        g = room.game
        if room.phase != "game" or g is None or g.finished or g.phase not in g.READING:
            raise HubError("not_now", "Nothing to skip right now")
        seen = msg.get("stage")
        if not isinstance(seen, str) or seen != g.stage:
            return False  # that screen already moved on
        if pid not in g.player_ids:
            raise HubError("players_only", "You're not in this game")
        if room.ready_stage != g.stage:
            room.ready_stage, room.ready = g.stage, set()
        room.ready.add(pid)
        if {p for p in g.player_ids if p in online} <= room.ready:
            room.ready, room.ready_stage = set(), ""
            g.advance()
            self._maybe_finish(room)
        return True

    def _maybe_finish(self, room: Room) -> None:
        game = room.game
        if game is None or not game.finished or room.phase != "game":
            return
        scores = game.scores()
        s = room.show
        if game.game_id != "jackpot":
            scores, room.card_news = showlib.apply_cards(self._plays(room), scores)
        if s is not None and game.game_id != "jackpot":
            room.rival_news = showlib.settle_rivals(room.rivals, scores)
            for r in room.rival_news:
                if r["winner"] is not None:
                    scores[r["winner"]] = scores.get(r["winner"], 0) + showlib.RIVAL_BONUS
        for pid, pts in scores.items():
            room.total_scores[pid] = room.total_scores.get(pid, 0) + pts
        if room.teams:
            totals = [sum(v for p, v in scores.items() if room.teams.get(p) == t) for t in (0, 1)]
            room.team_news = {
                "scores": totals,
                "winner": 0 if totals[0] > totals[1] else 1 if totals[1] > totals[0] else None,
            }
        room.phase = "results"
        self._scare_everyone_matched(room)  # the scores are up: boo
        names = room.names()
        try:
            room.highlights = game.highlights()
        except Exception:  # a highlight bug must never cost anyone their result
            log.exception("highlights failed")
            room.highlights = []
        final = "jackpot" if game.game_id == "jackpot" else None
        room.quip = showlib.quip(scores, names, game.title, room.decks, self.rng, final)
        if scores:  # the crowd's predictions: everyone who backed a winner gets a point
            top = max(scores.values())
            for au, target in room.predictions.items():
                watcher = room.audience.get(au)
                if watcher is not None and scores.get(target) == top:
                    watcher.points += 1
        if room.show is not None and room.show.market is not None and game.game_id != "jackpot":
            for pid in scores:
                room.show.market.seat(pid)
            room.market_moves = room.show.market.reprice(scores)
            top = max(scores.values(), default=0)
            winners = [p for p, v in scores.items() if v == top] if scores else []
            room.market_dividends = room.show.market.pay_dividends(winners)
        if room.show is not None:
            room.show.games.append({"game": game.game_id, "title": game.title, "scores": dict(scores)})
            room.show.reel.extend({**h, "game": game.title} for h in room.highlights)
        if self.on_game_finished:
            try:
                self.on_game_finished(game.game_id, game.summary())
            except Exception:
                log.exception("failed to record game result")
        self._pay_coins(room, game, scores)
        self._rate(room, game, scores)
        self._settle_battle(room, game, scores)

    def _settle_battle(self, room: Room, game: Game, scores: dict[str, int]) -> None:
        """The room's battle has been played: pay its prizes from the final scores (once)."""
        b = room.battle
        if not b or game.game_id != b["game"] or self.on_battle is None:
            return
        room.battle = {}  # played: the room goes on as a normal one
        accounts = self._paid_accounts(room)
        online = {p.id for p in room.connected_players()}
        placing = ratinglib.ranks({p: v for p, v in scores.items() if p in online})
        last = max(placing.values(), default=0) + 1
        by_account = {accounts[p]: placing.get(p, last) for p in scores if p in accounts}
        finished = {accounts[p] for p in scores if p in accounts and p in online}
        quick = self._too_quick(room)
        try:
            task = asyncio.get_running_loop().create_task(
                self._battle_paid(room, room.game_no, int(b["id"]), by_account, finished, quick)
            )
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _battle_paid(
        self,
        room: Room,
        game_no: int,
        battle_id: int,
        placing: dict[int, int],
        finished: set[int],
        quick: bool,
    ) -> None:
        if self.on_battle is None:
            return
        try:
            paid = await self.on_battle(battle_id, placing, finished, quick)
        except Exception:
            log.exception("could not pay a battle")
            return
        if paid is None or room.game_no != game_no:
            return
        seat = {uid: pid for pid, uid in room.accounts.items()}
        room.battle_news = {seat[u]: r for u, r in paid.items() if u in seat}
        await self.broadcast(room)

    def _rate(self, room: Room, game: Game, scores: dict[str, int]) -> None:
        """A ranked game's ratings, from the server's final scores. Anyone who left before the end is
        placed last."""
        if not room.ranked or self.on_rated is None or self._too_quick(room):
            return
        accounts = self._paid_accounts(room)
        online = {p.id for p in room.connected_players()}
        stayed = {p: v for p, v in scores.items() if p in online}
        placing = ratinglib.ranks(stayed)
        last = max(placing.values(), default=0) + 1
        by_account = {accounts[p]: placing.get(p, last) for p in scores if p in accounts}
        try:
            task = asyncio.get_running_loop().create_task(
                self._rated(room, room.game_no, game.game_id, by_account)
            )
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _rated(self, room: Room, game_no: int, game_id: str, placing: dict[int, int]) -> None:
        if self.on_rated is None:
            return
        try:
            changes = await self.on_rated(game_id, placing)
        except Exception:
            log.exception("could not rate a ranked game")
            return
        if room.game_no != game_no:
            return
        seat = {uid: pid for pid, uid in room.accounts.items()}
        if changes is None:  # didn't count: say so rather than show nothing
            room.rating_news = {seat[u]: {"counted": False} for u in placing if u in seat}
        else:
            room.rating_news = {seat[u]: {"counted": True, **c} for u, c in changes.items() if u in seat}
        await self.broadcast(room)

    async def tick(self) -> None:
        for room in list(self.rooms.values()):
            if not (host := room.players.get(room.host_id)) or not host.connected:
                async with room.lock:
                    moved = self._hand_over(room)
                if moved:
                    await self.broadcast(room)
            if room.phase == "market" and self.clock() >= room.market_until:
                async with room.lock:
                    self._close_market(room)
                await self.broadcast(room)
                continue
            if room.phase == "intro" and self.clock() >= room.intro_until:
                async with room.lock:
                    self._close_intro(room)
                await self.broadcast(room)
                continue
            game = room.game
            if game is None or room.phase != "game":
                continue
            async with room.lock:
                before = game.version
                game.tick()
                self._maybe_finish(room)
                changed = game.version != before
            if changed:
                await self.broadcast(room)

    # 0.2 s: timers (a Chicken Run bomb, a turn clock) fire within a fifth of a second of their time.
    async def run_ticker(self, interval: float = 0.2) -> None:
        while True:
            try:
                await self.tick()
                self.cleanup()
            except Exception:
                log.exception("ticker error")
            await asyncio.sleep(interval)
