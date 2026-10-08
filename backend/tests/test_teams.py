"""Team mode: the host's Teams switch (who can, which games, how many), the shuffle on the intro screen,
team totals and coins by team place at the results, and the official partner rules in Last Card and
Ludo."""

from __future__ import annotations

import asyncio
import random
import unittest

from app.config import Settings
from app.games import REGISTRY, GameError, Player
from app.games.lastcard import CARDS, LastCard
from app.games.ludo import HOME, YARD, Ludo
from app.rooms import INTRO_SECONDS, Hub
from tests.test_rooms import FAST, Clock, FakeConn


class Wallet:
    def __init__(self) -> None:
        self.paid: list = []

    async def pay(self, rows):
        self.paid.append(rows)
        return {r["user_id"]: r["coins"] for r in rows}


async def party(n: int, intro: bool = False, wallet: Wallet | None = None):
    hub = Hub(
        Settings(secret_key="s" * 40),
        clock=Clock(),
        rng=random.Random(4),
        timings=FAST,
        intro_seconds=INTRO_SECONDS if intro else 0,
        on_results=wallet.pay if wallet else None,
    )
    room, host, _ = hub.create_room("Host", user_id=100)
    conns = {host.id: FakeConn()}
    await hub.connect(room, host.id, conns[host.id])
    for i in range(n - 1):
        _, p, _ = hub.join_room(room.code, f"Guest{i}", user_id=101 + i)
        conns[p.id] = FakeConn()
        await hub.connect(room, p.id, conns[p.id])
    return hub, room, host.id, conns


class SwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_who_can_switch_teams_on_and_for_what(self):
        hub, room, host, conns = await party(3)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "truthdare", "teams": True})
        self.assertIn("too_few", conns[host].errors())  # 2 v 1 isn't a team game
        hub, room, host, conns = await party(4)
        guest = next(p for p in conns if p != host)
        await hub.handle_message(
            room, guest, conns[guest], {"t": "start", "game": "truthdare", "teams": True}
        )
        self.assertIn("not_host", conns[guest].errors())
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price", "teams": True})
        self.assertIn("no_teams", conns[host].errors())
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "truthdare", "teams": "yes"})
        self.assertIn("bad_message", conns[host].errors())
        self.assertEqual(room.phase, "lobby")
        self.assertEqual(
            {g for g, cls in REGISTRY.items() if cls.TEAMS}, {"ludo", "truthdare", "lastcard", "blackjack"}
        )

    async def test_the_intro_shows_two_even_teams_and_the_host_can_shuffle(self):
        hub, room, host, conns = await party(5, intro=True)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "blackjack", "teams": True})
        teams = conns[host].last["teams"]
        self.assertEqual(sorted(map(len, teams["members"])), [2, 3])
        self.assertIn(teams["you"], (0, 1))
        guest = next(p for p in conns if p != host)
        await hub.handle_message(room, guest, conns[guest], {"t": "shuffle"})
        self.assertIn("not_host", conns[guest].errors())
        seen = {tuple(map(tuple, teams["members"]))}
        for _ in range(6):
            await hub.handle_message(room, host, conns[host], {"t": "shuffle"})
            seen.add(tuple(map(tuple, conns[host].last["teams"]["members"])))
        self.assertGreater(len(seen), 1)
        final = conns[host].last["teams"]["members"]
        await hub.handle_message(room, host, conns[host], {"t": "skip"})  # the host starts it now
        self.assertEqual(room.phase, "game")
        self.assertEqual(conns[guest].last["teams"]["members"], final)  # the teams that were shown

    async def test_team_totals_win_and_coins_go_by_team_place(self):
        wallet = Wallet()
        hub, room, host, conns = await party(4, wallet=wallet)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "truthdare", "teams": True})
        self.assertEqual(room.phase, "game")
        tv_room, tv_token = hub.issue_tv(room.code)
        tv_id = next(iter(room.viewers))
        self.assertIsNone(hub.view_for(room, tv_id)["teams"]["you"])
        self.assertIsNone(conns[host].last["teams"]["news"])  # no result mid-game
        for _ in range(400):
            if room.phase != "game":
                break
            room.game.advance()
            hub._maybe_finish(room)
        await asyncio.gather(*list(hub._tasks))
        scores = room.game.scores()
        totals = [sum(v for p, v in scores.items() if room.teams[p] == t) for t in (0, 1)]
        self.assertEqual(room.team_news["scores"], totals)
        rows = wallet.paid[0]
        by_team = {room.teams[r["pid"]]: r["place"] for r in rows}
        for r in rows:  # teammates share their team's place, whatever they scored alone
            self.assertEqual(r["place"], by_team[room.teams[r["pid"]]])
        if totals[0] != totals[1]:
            winner = 0 if totals[0] > totals[1] else 1
            self.assertEqual(room.team_news["winner"], winner)
            self.assertEqual(by_team[winner], 1)

    async def test_without_the_switch_there_are_no_teams(self):
        hub, room, host, conns = await party(4)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "truthdare"})
        self.assertIsNone(conns[host].last["teams"])
        self.assertEqual(room.teams, {})


class PartnerRuleTests(unittest.TestCase):
    def players(self, n):
        return [Player(id=f"p{i}", name=f"N{i}") for i in range(n)]

    def test_last_card_partners_sit_opposite_and_score_only_the_other_team(self):
        teams = {"p0": 0, "p1": 0, "p2": 1, "p3": 1}
        g = LastCard(self.players(4), rng=random.Random(2), teams=teams)
        g.start()
        sides = [teams[p] for p in g.order]
        self.assertTrue(all(a != b for a, b in zip(sides, sides[1:] + sides[:1], strict=True)))
        red7 = next(i for i, (c, v) in enumerate(CARDS) if (c, v) == ("red", "7"))
        nines = [i for i, (c, v) in enumerate(CARDS) if v == "9"]
        winner = g.order[0]
        partner = next(p for p in g.order if p != winner and teams[p] == teams[winner])
        g.hands = {p: [nines[i]] for i, p in enumerate(g.order)}
        g.hands[winner] = [red7]
        g.discard, g.color, g.turn, g.pending, g.drawn = [red7 + 1], "red", 0, None, None
        g.handle(winner, {"a": "play", "card": red7})
        self.assertEqual(g.phase, "hand_over")
        self.assertEqual(g.scores()[winner], 18)  # two rivals' nines; the partner's nine doesn't count
        self.assertEqual(g.scores()[partner], 0)

    def test_ludo_partners_play_opposite_colours_and_win_together(self):
        teams = {"p0": 0, "p1": 1, "p2": 0, "p3": 1}
        g = Ludo(self.players(4), rng=random.Random(3), teams=teams)
        g.start()
        team_of = {c: teams[g.members[c][0]] for c in g.colors}
        self.assertEqual(team_of["red"], team_of["yellow"])
        self.assertEqual(team_of["green"], team_of["blue"])
        self.assertNotEqual(team_of["red"], team_of["green"])
        g.tokens = {
            "red": [HOME] * 4,
            "green": [YARD] * 4,
            "yellow": [HOME, HOME, HOME, 55],
            "blue": [YARD] * 4,
        }
        g.places = ["red"]
        g.turn, g.rolled, g.rng = 2, None, type("D", (), {"randint": lambda self, a, b: 1})()
        g.handle(g.current, {"a": "roll"})  # yellow home: red + yellow are both home
        self.assertTrue(g.finished)
        self.assertEqual(g.places[:2], ["red", "yellow"])
        with self.assertRaises(GameError):
            Ludo(self.players(6), rng=random.Random(1), teams={f"p{i}": i % 2 for i in range(6)}).start()


if __name__ == "__main__":
    unittest.main()
