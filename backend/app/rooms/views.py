"""What each screen is sent: the room view and its parts."""

from __future__ import annotations

from typing import Any

from .. import calls
from .. import show as showlib
from ..games import REGISTRY, catalog, catalogue
from ..games.content import THEMES
from ..games.jackpot import Jackpot
from .models import (
    FAN_BONUS,
    Room,
)


class ViewsMixin:
    # -- views --------------------------------------------------------------
    def view_for(self, room: Room, pid: str) -> dict[str, Any]:
        game_view = None
        if room.game is not None and room.phase in ("game", "results"):
            game_view = room.game.view_for(pid)
        between = room.phase in ("lobby", "results", "finale")
        role = "tv" if pid in room.viewers else "audience" if pid in room.audience else "player"
        return {
            "t": "state",
            "you": pid,
            "tv": role == "tv",
            "role": role,
            "room": {
                "code": room.code,
                "phase": room.phase,
                "host": room.host_id,
                "title": room.title,
                "locked": room.locked,
                "theme": room.theme,
            },
            "themes": THEMES if between else {},
            "show": self._show_view(room),
            "highlights": room.highlights if room.phase == "results" else [],
            "quip": room.quip if room.phase in ("results", "finale") else "",
            "reactions": room.reactions,
            "chat": self._chat_view(room, pid),
            "call": {
                "available": calls.enabled(self.settings),
                "allowed": self._call_allowed(room, pid),
                "hush": room.call_hush,
            },
            "faces": room.faces,
            "night": self._night_view(room),
            "entrance": room.entrance or None,
            "crowd": self._crowd_view(room, pid),
            "market": self._market_view(room, pid),
            "cards": self._cards_view(room, pid),
            "rivals": {
                "pairs": [list(p) for p in room.rivals] if room.phase in ("game", "results") else [],
                "news": room.rival_news if room.phase == "results" else [],
                "bonus": showlib.RIVAL_BONUS,
            },
            "season": {"number": room.season_no, "table": room.season} if room.season_no else None,
            "intro": self._intro_view(room) if room.phase == "intro" else None,
            "teams": self._teams_view(room, pid),
            "ranked": {
                "on": room.ranked if room.phase in ("game", "results") else bool(room.intro.get("ranked")),
                "news": room.rating_news if room.phase == "results" else {},
                # everyone online has their own account (never who doesn't): a ranked game can start
                "ready": self._all_signed_in(room),
            },
            "party": {
                "effects": [{k: e[k] for k in ("id", "item", "by")} for e in room.party_effects],
            },
            "powers": {
                "offer": [{"id": k, **v} for k, v in self._power_offer(room).items()]
                if pid in room.players and pid in room.accounts
                else [],
                "used": room.power_used.get(pid) == room.game_no and room.phase == "game",
                "news": room.power_news if room.phase in ("game", "results") else [],
                "mine": room.power_private.get(pid) if room.phase == "game" else None,
            },
            "battle": {
                "game": room.battle.get("game") if room.battle else None,
                "kind": room.battle.get("kind") if room.battle else None,
                "news": room.battle_news if room.phase == "results" else {},
            },
            "ready": self._ready_view(room),
            "last_standings": room.last_standings if room.phase == "lobby" else [],
            "scare": room.scares.get(pid, 0),  # only ever this viewer's own count
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "connected": p.connected,
                    "host": p.id == room.host_id,
                    "total": room.total_scores.get(p.id, 0),
                }
                for p in room.players.values()
            ],
            "games": [g for g in catalog() if not room.club_games or g["id"] in room.club_games]
            if between
            else [],
            "categories": catalogue.categories() if between else [],
            "game": game_view,
            "stage": room.game.stage if room.game is not None else None,
            "how_to": list(room.game.HOW_TO) if game_view is not None and room.game is not None else [],
        }

    @staticmethod
    def _show_view(room: Room) -> dict[str, Any] | None:
        s = room.show
        if s is None:
            return None
        titles = {gid: cls.title for gid, cls in REGISTRY.items()} | {"jackpot": Jackpot.title}
        return {
            "playlist": [{"id": g, "title": titles.get(g, g)} for g in s.playlist],
            "jackpot": s.jackpot,
            "started": s.started,
            "next": s.next_game(),
            "finished": s.finished,
            "games": [{"game": g["game"], "title": g["title"], "scores": g["scores"]} for g in s.games],
            "reel": s.reel if s.finished else [],
            "awards": s.awards if s.finished else [],
            "market": s.market is not None,
            "can_rematch": bool(room.last_show),
        }

    def _teams_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        teams = room.intro.get("teams") if room.phase == "intro" else room.teams
        if not teams:
            return None
        return {
            "members": [[p for p, t in teams.items() if t == side] for side in (0, 1)],
            "you": teams.get(pid),
            "news": room.team_news if room.phase in ("results", "finale") else None,
        }

    def _intro_view(self, room: Room) -> dict[str, Any]:
        gid = room.intro.get("game", "")
        cls = Jackpot if gid == "jackpot" else REGISTRY.get(gid)
        online = [p.id for p in room.connected_players()]
        return {
            "game": gid,
            "title": cls.title if cls else gid,
            "blurb": cls.blurb if cls else "",
            "how_to": list(cls.HOW_TO) if cls else [],
            "options": dict(room.intro.get("options", {})),
            "closes_in": max(0.0, room.intro_until - self.clock()),
            "ready": sorted(p for p in room.ready if p in online),
            "needed": len(online),
        }

    def _ready_view(self, room: Room) -> dict[str, Any]:
        """A results/briefing screen everyone can skip together."""
        g = room.game
        open_ = room.phase == "game" and g is not None and not g.finished and g.phase in g.READING
        votes = sorted(room.ready) if open_ and room.ready_stage == (g.stage if g else "") else []
        return {
            "open": open_,
            "stage": g.stage if open_ and g is not None else "",
            "votes": votes,
            "needed": len([p for p in g.player_ids if room.players.get(p) and room.players[p].connected])
            if open_ and g is not None
            else 0,
        }

    @staticmethod
    def _standing(room: Room) -> tuple[str | None, str | None]:
        """(the clear leader, the last-placed player) by tonight's totals; None while nothing separates
        them (no points yet, or a tie at the top)."""
        totals = {p: room.total_scores.get(p, 0) for p in room.players}
        if len(totals) < 2 or len(set(totals.values())) < 2:
            return None, None
        top = max(totals.values())
        leaders = [p for p, t in totals.items() if t == top]
        low = min(totals.values())
        return (leaders[0] if len(leaders) == 1 else None), min(p for p, t in totals.items() if t == low)

    def _night_view(self, room: Room) -> dict[str, Any]:
        """The champion's belt and the loser's wheel."""
        holder = next(
            (p.id for p in room.players.values() if p.name.casefold() == room.belt.casefold()), None
        )
        leader, last = self._standing(room)
        return {
            "belt": {"name": room.belt, "holder": holder if room.belt else None},
            "leader": leader,
            "last": last,
            "forfeits": list(room.forfeits),
            "wheel": room.wheel or None,
        }

    def _cards_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        s = room.show
        if s is None and not room.accounts:
            return None
        this_game = self._plays(room) if room.phase == "game" else []
        played = next((p for p in s.plays if p["pid"] == pid), None) if s else None
        boost = next((p for p in this_game if p.get("bought") and p["pid"] == pid), None)
        return {
            "catalog": showlib.CARDS,
            "in_play": len(this_game),  # how many cards are down this game: never whose or which
            "news": room.card_news if room.phase == "results" else [],  # the reveal
            "coins": room.coin_news if room.phase in ("results", "finale") else {},
            "you": {
                "card": s.cards.get(pid) if s else None,
                "played": played["card"] if played else None,
                "peek": (s.peeks.get(pid) if s else None) or room.boost_peeks.get(pid),
                "signed_in": pid in room.accounts,  # can use power-ups bought with coins
                "boost": boost["card"] if boost else None,  # the one used this game
            }
            if pid in room.players
            else None,
        }

    def _plays(self, room: Room) -> list[dict[str, Any]]:
        """Every card and power-up played on the current game."""
        s = room.show
        shown = [p for p in s.plays if p["game"] == len(s.games)] if s is not None else []
        return shown + [b for b in room.boosts if b["game"] == room.game_no]

    def _market_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        m = room.show.market if room.show else None
        if m is None:
            return None
        titles = {gid: cls.title for gid, cls in REGISTRY.items()}
        finale = room.phase == "finale"
        mine = pid in room.players or pid in room.audience
        return {
            "open": room.phase == "market",
            "closes_in": max(0.0, room.market_until - self.clock()) if room.phase == "market" else None,
            "next": titles.get(room.market_next, room.market_next) if room.phase == "market" else "",
            "prices": dict(m.prices),
            "history": [dict(h) for h in m.history],
            "moves": dict(room.market_moves),
            "dividends": dict(room.market_dividends) if room.phase == "results" else {},
            "dividend": showlib.DIVIDEND,
            "trades": m.trades,
            # Your own book only; everyone's is revealed at the finale.
            "you": {
                # The audience is seated on their first trade: until then they hold the starting cash.
                "cash": m.cash.get(pid, showlib.START_CASH),
                "holdings": dict(m.holdings.get(pid, {})),
                "worth": m.worth(pid) if pid in m.cash else showlib.START_CASH,
                "tip": room.tip if pid == room.insider and room.phase == "market" else "",
            }
            if mine
            else None,
            # Audience traders, named at the finale so their books can be shown.
            "crowd": {w.id: w.name for w in room.audience.values() if w.id in m.cash} if finale else {},
            "worth": {p: m.worth(p) for p in m.cash} if finale else {},
            "books": {p: dict(h) for p, h in m.holdings.items()} if finale else {},
            "bonus": {p: m.bonus(p) for p in m.cash} if finale else {},
        }

    @staticmethod
    def _predict_open(room: Room) -> bool:
        g = room.game
        return room.phase == "game" and g is not None and not g.finished and g.round <= 1

    def _crowd_view(self, room: Room, pid: str) -> dict[str, Any]:
        picks: dict[str, int] = {}
        for target in room.predictions.values():
            picks[target] = picks.get(target, 0) + 1
        return {
            "members": [
                {"id": w.id, "name": w.name, "points": w.points, "connected": w.conn is not None}
                for w in room.audience.values()
            ],
            # who can be backed this game: the game's own contestants (not everyone ever seated)
            "contestants": [{"id": p.id, "name": p.name} for p in room.game.players]
            if room.game is not None and room.phase in ("game", "results")
            else [],
            "picks": picks,  # how many of the crowd back each player this game (never who)
            "open": self._predict_open(room),
            "you_picked": room.predictions.get(pid),
            "mvp": {
                "open": self._mvp_open(room),
                "you_voted": room.mvp_votes.get(pid),
                "votes": self._tally(room.mvp_votes),
                "bonus": FAN_BONUS,
            },
        }

    @staticmethod
    def _tally(votes: dict[str, str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for target in votes.values():
            out[target] = out.get(target, 0) + 1
        return out

    @staticmethod
    def _mvp_open(room: Room) -> bool:
        return room.phase == "results" and room.show is not None and room.game is not None
