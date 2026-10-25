"""Show nights: the playlist, market, power cards, boosts, coins, MVP, finale, belt and forfeits."""

from __future__ import annotations

import asyncio
from typing import Any

from .. import coins as coinlib
from .. import fairplay
from .. import show as showlib
from ..games import REGISTRY, Game
from .models import (
    DEFAULT_FORFEITS,
    FAN_BONUS,
    FORFEIT_MAX,
    MARKET_SECONDS,
    MAX_FORFEITS,
    WHEEL_GAP,
    WHEEL_SLOTS,
    HubError,
    Room,
    clean_chat,
    log,
)


class ShowMixin:
    def _keep_circle(self, room: Room) -> None:
        uid = room.accounts.get(room.host_id)
        if self.save_circle is None or uid is None:
            return
        task = asyncio.get_running_loop().create_task(self.save_circle(uid, room.belt, list(room.forfeits)))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _night(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        """Between games: crown tonight's champion, edit the forfeits, spin the loser's wheel."""
        is_host = pid == room.host_id
        if room.phase in ("game", "intro", "market"):
            raise HubError("in_progress", "Wait until the game is over", 409)
        leader, last = self._standing(room)
        if kind == "crown":
            if not is_host:
                raise HubError("not_host", "Only the host hands out the belt", 403)
            if leader is None:
                raise HubError("no_leader", "Nobody is clearly in front yet")
            name = room.players[leader].name
            room.belt = name
            room.entrance = {
                "id": room.entrance.get("id", 0) + 1,
                "pid": leader,
                "name": name,
                "kind": "belt",
            }
            self._keep_circle(room)
            return True
        if kind == "forfeit":
            if not is_host:
                raise HubError("not_host", "Only the host edits the forfeits", 403)
            if "del" in msg:
                i = msg["del"]
                if type(i) is not int or not 0 <= i < len(room.forfeits):
                    raise HubError("bad_message", "Unknown message")
                del room.forfeits[i]
            else:
                text = clean_chat(msg.get("add"))
                if len(text) > FORFEIT_MAX:
                    raise HubError("too_long", f"Forfeits are up to {FORFEIT_MAX} characters")
                if len(room.forfeits) >= MAX_FORFEITS:
                    raise HubError("full", "That's plenty of forfeits")
                if text.casefold() in (f.casefold() for f in room.forfeits):
                    raise HubError("duplicate", "That one's already on the wheel")
                room.forfeits.append(text)
            self._keep_circle(room)
            return True
        # the wheel: the loser spins it themselves (the host can do it for them)
        if last is None:
            raise HubError("no_loser", "Nobody is clearly last yet")
        if not is_host and pid != last:
            raise HubError("not_yours", "Only last place (or the host) spins the wheel", 403)
        now = self.clock()
        if now - room.call_last.get("wheel", -1e9) < WHEEL_GAP:
            raise HubError("slow_down", "The wheel is still spinning")
        room.call_last["wheel"] = now
        spare = [f for f in DEFAULT_FORFEITS if f.casefold() not in {x.casefold() for x in room.forfeits}]
        self.rng.shuffle(spare)
        pool = list(room.forfeits)
        self.rng.shuffle(pool)
        options = (pool + spare)[:WHEEL_SLOTS] if len(pool) < WHEEL_SLOTS else pool[:WHEEL_SLOTS]
        self.rng.shuffle(options)
        room.wheel = {
            "n": room.wheel.get("n", 0) + 1,
            "pid": last,
            "name": room.players[last].name,
            "options": options,
            "pick": self.rng.randrange(len(options)),
        }
        return True

    async def _use_boost(self, room: Room, pid: str, msg: dict[str, Any]) -> None:
        """Use a power-up bought with coins on the game being played: one per player per game."""
        item = msg.get("item")
        target = msg.get("target")
        async with room.lock:
            game_no = self._check_boost(room, pid, item, target)
        user_id = room.accounts[pid]
        if self.spend_powerup is None or not await self.spend_powerup(user_id, str(item)):
            raise HubError("no_powerup", "You don't have that power-up. Buy one in the shop")
        async with room.lock:
            try:
                if room.game_no != game_no:
                    raise HubError("too_late", "That game has finished")
                self._check_boost(room, pid, item, target)
                play: dict[str, Any] = {"pid": pid, "card": item, "game": game_no, "bought": True}
                if item == "steal":
                    play["target"] = target
                if item == "peek":
                    seen = room.game.peek(pid) if room.game is not None else None
                    if not seen:
                        raise HubError("nothing_to_peek", "Nothing to peek at in this game right now")
                    room.boost_peeks[pid] = seen
                room.boosts = [b for b in room.boosts if b["game"] == game_no] + [play]
            except Exception:
                if self.refund_powerup is not None:
                    await self.refund_powerup(user_id, str(item))
                raise

    # -- power-ups v2: a game's own POWERS, seen by the whole room ------------------------------------
    def _power_offer(self, room: Room) -> dict[str, dict[str, str]]:
        """The power-ups this room's game offers right now: casual rooms only (never ranked or battles)."""
        game = room.game
        if room.phase != "game" or game is None or game.finished or room.ranked or room.battle:
            return {}
        return dict(game.POWERS)

    def _check_power(self, room: Room, pid: str, item: Any) -> int:
        if pid not in room.accounts:
            raise HubError("signed_out", "Sign in to use power-ups")
        if room.ranked or room.battle:
            raise HubError("no_power", "Power-ups are off in ranked games and battles")
        offer = self._power_offer(room)
        if not isinstance(item, str) or item not in offer or room.game is None:
            raise HubError("no_power", "That power-up isn't in this game")
        if pid not in room.game.player_ids:
            raise HubError("no_power", "You're not in this game")
        if room.power_used.get(pid) == room.game_no:
            raise HubError("already_used", "One power-up per game")
        return room.game_no

    async def _use_power(self, room: Room, pid: str, msg: dict[str, Any]) -> None:
        """Spend one of your power-ups on the game being played. The room sees who used what; anything
        it shows (a struck answer, a die) goes only to you. Given back if the game can't use it now."""
        item = msg.get("item")
        async with room.lock:
            game_no = self._check_power(room, pid, item)
        user_id = room.accounts[pid]
        if self.spend_powerup is None or not await self.spend_powerup(user_id, str(item)):
            raise HubError("no_powerup", "You don't have that power-up. Buy one in the shop")
        async with room.lock:
            try:
                if room.game_no != game_no:
                    raise HubError("too_late", "That game has finished")
                self._check_power(room, pid, item)
                game = room.game
                if game is None:
                    raise HubError("too_late", "That game has finished")
                line = game.use_power(pid, str(item))
                room.power_used[pid] = game_no
                info = game.POWERS[str(item)]
                room.power_news = [
                    *room.power_news[-7:],
                    {"pid": pid, "item": str(item), "name": info["name"], "icon": info["icon"]},
                ]
                if line:
                    room.power_private[pid] = line
            except Exception:
                if self.refund_powerup is not None:
                    await self.refund_powerup(user_id, str(item))
                raise

    def _check_boost(self, room: Room, pid: str, item: Any, target: Any) -> int:
        game = room.game
        if pid not in room.accounts:
            raise HubError("signed_out", "Sign in to use power-ups")
        if room.ranked:
            raise HubError("ranked", "Power-ups are off in ranked games")
        if room.battle:
            raise HubError("battle", "Power-ups are off in battles")
        if room.phase != "game" or game is None or game.finished or game.game_id == "jackpot":
            raise HubError("no_card", "Power-ups are used during a game")
        if pid not in game.player_ids:
            raise HubError("no_card", "You're not in this game")
        if item not in coinlib.POWERUP_PRICES:
            raise HubError("bad_item", "That's not a power-up")
        if any(b["pid"] == pid and b["game"] == room.game_no for b in room.boosts):
            raise HubError("already_used", "One power-up per game")
        if item in showlib.EARLY_CARDS and not self._predict_open(room):
            raise HubError("too_late", "That one only works before the first round is over")
        if item == "steal" and (
            not isinstance(target, str) or target == pid or target not in game.player_ids
        ):
            raise HubError("bad_target", "Pick a rival in this game")
        return room.game_no

    def _pay_coins(self, room: Room, game: Game, scores: dict[str, int]) -> None:
        """Coins for every signed-in finisher (one result per account), paid in the background."""
        accounts = self._paid_accounts(room)
        if self.on_results is None or game.game_id == "jackpot" or not accounts:
            return
        quick = self._too_quick(room)
        signed_in = set(accounts.values())
        group = fairplay.group_key(signed_in)
        if room.teams:  # teams: everyone finishes where their team does
            totals = {t: sum(v for p, v in scores.items() if room.teams.get(p) == t) for t in (0, 1)}
            team_place = coinlib.places({str(t): v for t, v in totals.items()})
            placed = {p: team_place[str(room.teams[p])] for p in scores if p in room.teams}
            all_tied = len(set(totals.values())) == 1
        else:
            placed = coinlib.places(scores)
            all_tied = len(set(scores.values())) == 1
        best: dict[int, dict[str, Any]] = {}
        for pid, place in placed.items():
            uid = accounts.get(pid)
            if uid is None:
                continue
            due = coinlib.coins_for(place, len(scores), all_tied=all_tied)
            coins, note = (0, "quick") if quick else fairplay.solo_coins(due, len(signed_in))
            row = {
                "user_id": uid,
                "pid": pid,
                "game_id": game.game_id,
                "place": place,
                "players": len(scores),
                "points": scores[pid],
                "coins": coins,
                "note": note,
                "group": group,
                "accounts": len(signed_in),
            }
            if uid not in best or place < best[uid]["place"]:
                best[uid] = row
        if not best:
            return
        try:
            task = asyncio.get_running_loop().create_task(
                self._coins_landed(room, room.game_no, list(best.values()))
            )
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _coins_landed(self, room: Room, game_no: int, rows: list[dict[str, Any]]) -> None:
        if self.on_results is None:
            return
        try:
            paid = await self.on_results(rows)
        except Exception:
            log.exception("could not pay coins")
            return
        if room.game_no != game_no:
            return
        room.coin_news = {
            r["pid"]: {
                "place": r["place"],
                "coins": paid.get(r["user_id"], {}).get("coins", 0),
                "note": paid.get(r["user_id"], {}).get("note", r.get("note", "")),
                "xp": paid.get(r["user_id"], {}).get("xp", 0),
            }
            for r in rows
        }
        await self.broadcast(room)

    def _award_mvp(self, room: Room) -> None:
        """The audience's MVP of the game that just ended: +FAN_BONUS each for the top vote (ties share)."""
        votes = self._tally(room.mvp_votes)
        room.mvp_votes = {}
        if not votes or room.show is None:
            return
        top = max(votes.values())
        names = room.names()
        for pid in (p for p, v in votes.items() if v == top and p in room.players):
            room.total_scores[pid] = room.total_scores.get(pid, 0) + FAN_BONUS
            title = room.show.games[-1]["title"] if room.show.games else ""
            room.show.reel.append(
                {
                    "icon": "⭐",
                    "title": "Fan favourite",
                    "text": f"The crowd voted {names.get(pid, '?')} MVP (+{FAN_BONUS})",
                    "game": title,
                }
            )

    def _start_next(self, room: Room, s: showlib.Show) -> None:
        """Start the show's next segment, or close the show with the finale."""
        self._award_mvp(room)
        nxt = s.next_game()
        if nxt == "jackpot":
            self._open_intro(room, "jackpot", slot="jackpot")
        elif nxt is not None:
            self._make_game(room, REGISTRY[nxt])  # raises (e.g. too few players) before anything moves
            if s.market is not None:
                self._open_market(room, nxt)
            else:
                self._open_intro(room, nxt, slot="playlist")
        else:
            self._finale(room, s)

    def _open_market(self, room: Room, game_id: str) -> None:
        """Trading window before a show game. The game itself is built when the bell rings."""
        market = room.show.market if room.show else None
        room.insider, room.tip = "", ""
        if market is not None:
            for pid in room.players:
                market.seat(pid)
            online = [p.id for p in room.connected_players()]
            if online:  # one random player gets an insider tip: someone else's secret book
                room.insider = self.rng.choice(online)
                names = room.names() | {w.id: w.name for w in room.audience.values()}
                room.tip = market.tip(room.insider, self.rng, names)
        room.game, room.phase = None, "market"
        room.market_next = game_id
        room.market_until = self.clock() + MARKET_SECONDS
        room.predictions, room.highlights, room.quip = {}, [], ""

    def _close_market(self, room: Room) -> None:
        s = room.show
        if s is None or room.phase != "market":
            return
        self._open_intro(room, room.market_next, slot="playlist")

    def _start_show(self, room: Room, games: list[str], jackpot: bool, market: bool) -> None:
        game = self._make_game(room, REGISTRY[games[0]])  # raises before anything changes
        room.total_scores = {p: 0 for p in room.players}  # a new show, a fresh scoreboard
        room.last_show = {"games": list(games), "jackpot": jackpot, "market": market}
        del game  # only built to check the room can play it
        if market:
            room.show = showlib.Show(playlist=list(games), jackpot=jackpot, market=showlib.Market())
            self._open_market(room, games[0])
        else:
            room.show = showlib.Show(playlist=list(games), jackpot=jackpot)
            self._open_intro(room, games[0], slot="playlist")

    def _play_card(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        """Play your one power card on the game being played. Secret until that game's results."""
        s, game = room.show, room.game
        if pid not in room.players or s is None or game is None or room.phase != "game":
            raise HubError("no_card", "Cards are played during a show game")
        if game.game_id == "jackpot" or game.finished:
            raise HubError("no_card", "No cards in this game")
        if pid not in game.player_ids:
            raise HubError("no_card", "You're not in this game")
        card = s.cards.get(pid)
        if card is None:
            raise HubError("no_card", "You've played your card this show")
        play: dict[str, Any] = {"pid": pid, "card": card, "game": len(s.games)}
        if card in showlib.EARLY_CARDS and not self._predict_open(room):
            raise HubError("too_late", "That card only works before the first round is over")
        if card == "steal":
            target = msg.get("target")
            if not isinstance(target, str) or target == pid or target not in game.player_ids:
                raise HubError("bad_target", "Pick a rival in this game")
            play["target"] = target
        if card == "peek":
            try:
                seen = game.peek(pid)
            except Exception:  # a peek bug must never break the game
                log.exception("peek failed")
                seen = None
            if not seen:
                raise HubError("nothing_to_peek", "Nothing to peek at right now. Try again in a moment")
            s.peeks[pid] = seen
        del s.cards[pid]
        s.plays.append(play)
        return True

    def _finale(self, room: Room, s: showlib.Show) -> None:
        s.finished = True
        if s.market is not None:  # net worth becomes show points: $10 = 1 point, either way
            for pid in room.players:
                s.market.seat(pid)
                room.total_scores[pid] = room.total_scores.get(pid, 0) + s.market.bonus(pid)
        totals = {pid: room.total_scores.get(pid, 0) for pid in room.players}
        names = room.names()
        s.awards = showlib.awards(s, totals, names)
        if s.market is not None and room.players:
            tycoon = max(room.players, key=s.market.worth)
            worth = s.market.worth(tycoon)
            if worth > showlib.START_CASH:
                s.awards.append(
                    {
                        "icon": "📈",
                        "title": "Market tycoon",
                        "text": f"{names.get(tycoon, '?')} ended worth ${worth:,}",
                    }
                )
        if s.market is not None:
            fans = {w.id: w for w in room.audience.values() if w.id in s.market.cash}
            if fans:
                best = max(fans, key=s.market.worth)
                if s.market.worth(best) > showlib.START_CASH:
                    s.awards.append(
                        {
                            "icon": "🤑",
                            "title": "Crowd tycoon",
                            "text": f"{fans[best].name} (audience) ended worth ${s.market.worth(best):,}",
                        }
                    )
        s.quip = room.quip = showlib.quip(
            totals, names, room.title or "the show", room.decks, self.rng, "show"
        )
        # The season: every show in this room adds to a running table (shows won, points).
        room.season_no += 1
        top = max(totals.values(), default=0)
        for pid, pts in totals.items():
            row = room.season.setdefault(pid, {"wins": 0, "points": 0})
            row["points"] += pts
            if pts == top:
                row["wins"] += 1
        self._scare_everyone_matched(room)
        room.game, room.phase = None, "finale"
