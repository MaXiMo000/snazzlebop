"""Property Tycoon: movement, buying and auctions, rent, building, mortgages, jail, cards, debts and
bankruptcy, trades, the party clock, scoring, and what the views show."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.tycoon import FUND, GROUPS, SURPRISE, PropertyTycoon, board

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, dice=(), **opts):
    clock = Clock()
    g = PropertyTycoon(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    script = list(dice)
    real = g._roll_dice
    g._roll_dice = lambda: script.pop(0) if script else real()  # type: ignore[method-assign]
    g.script = script  # type: ignore[attr-defined]
    return g, clock


def roll(g, *dice):
    g.script.extend(dice)
    g.handle(g.current, {"a": "roll"})


def give(g, pid, *squares):
    for sq in squares:
        g.owner[sq] = pid


class BoardTests(unittest.TestCase):
    def test_board(self):
        b = board()
        self.assertEqual(len(b), 40)
        self.assertEqual(sum(1 for s in b if s["kind"] == "street"), 22)
        self.assertEqual(sorted(len(v) for v in GROUPS.values()), [2, 2, 3, 3, 3, 3, 3, 3])
        self.assertEqual(len(SURPRISE), 16)
        self.assertEqual(len(FUND), 16)
        names = [s["name"] for s in b]
        self.assertEqual(len(set(n for n, s in zip(names, b, strict=True) if s["kind"] == "street")), 22)


class MoveTests(unittest.TestCase):
    def test_move_buy_and_pass_go(self):
        g, _ = make()
        me = g.current
        self.assertEqual((g.phase, g.cash[me]), ("roll", 1500))
        roll(g, (1, 2))  # to Mossy Row (3)
        self.assertEqual((g.pos[me], g.phase, g.offer), (3, "buy", 3))
        g.handle(me, {"a": "buy"})
        self.assertEqual((g.owner[3], g.cash[me], g.phase), (me, 1440, "manage"))
        g.handle(me, {"a": "end"})
        self.assertNotEqual(g.current, me)
        g.pos[me] = 38
        g.current = me
        g.phase, g.must_roll = "roll", True
        roll(g, (2, 3))  # 38 -> 3: passes GO, lands on own street
        self.assertEqual((g.pos[me], g.cash[me]), (3, 1640))

    def test_doubles_roll_again_and_three_doubles_jail(self):
        g, _ = make()
        me = g.current
        roll(g, (2, 2))  # 4: Income Tax
        self.assertEqual((g.phase, g.cash[me]), ("roll", 1300))
        roll(g, (3, 3))  # 10: just visiting
        self.assertEqual(g.phase, "roll")
        roll(g, (1, 1))
        self.assertEqual((g.pos[me], me in g.jail, g.phase), (10, True, "manage"))

    def test_go_to_jail_square_and_getting_out(self):
        g, _ = make()
        me = g.current
        g.pos[me] = 25
        roll(g, (2, 3))  # 30: go to jail
        self.assertTrue(me in g.jail)
        self.assertEqual(g.pos[me], 10)
        g.handle(me, {"a": "end"})
        while g.current != me:
            g.handle(g.current, {"a": "roll"}) if g.phase == "roll" else None
            if g.phase == "buy":
                g.handle(g.current, {"a": "buy"})
            if g.phase == "debt":
                g.handle(g.current, {"a": "bankrupt"})
            if g.phase == "manage":
                g.handle(g.current, {"a": "end"})
        # three misses, then pay $50 and move
        for tries in (1, 2):
            roll(g, (1, 2))
            self.assertEqual((g.jail[me], g.pos[me]), (tries, 10))
            g.current = me
            g.phase, g.must_roll = "roll", True
        cash = g.cash[me]
        roll(g, (1, 3))
        self.assertNotIn(me, g.jail)
        self.assertEqual(g.pos[me], 14)
        self.assertEqual(g.cash[me], cash - 50 - (140 if g.phase == "buy" else 0) * 0)

    def test_jail_doubles_card_and_fine(self):
        g, _ = make()
        me = g.current
        g._to_jail(me)
        g.must_roll = True
        g._continue()
        roll(g, (4, 4))  # out on doubles, moves 8, no extra roll
        self.assertNotIn(me, g.jail)
        self.assertEqual(g.pos[me], 18)
        self.assertFalse(g.must_roll)
        g.free_cards[me].append("chance:7")
        g.piles["chance"].remove(7)
        g._to_jail(me)
        g.must_roll, g.offer = True, None
        g._continue()
        g.handle(me, {"a": "use_card"})
        self.assertNotIn(me, g.jail)
        self.assertIn(7, g.piles["chance"])
        g._to_jail(me)
        g.handle(me, {"a": "pay_fine"})
        self.assertNotIn(me, g.jail)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "pay_fine"})


class AuctionTests(unittest.TestCase):
    def test_decline_auction_and_bids(self):
        g, clock = make()
        me = g.current
        other = next(p for p in g.order if p != me)
        roll(g, (1, 2))
        g.handle(me, {"a": "decline"})
        self.assertEqual(g.phase, "auction")
        g.handle(other, {"a": "bid", "amount": 10})
        for bad in (10, 5, 0, "20", True, 999999):
            with self.assertRaises(GameError):
                g.handle(me, {"a": "bid", "amount": bad})
        g.handle(me, {"a": "bid", "amount": 30})
        clock.t += 100
        g.tick()
        self.assertEqual((g.owner[3], g.cash[me]), (me, 1470))
        self.assertEqual(g.phase, "manage")

    def test_nobody_bids(self):
        g, clock = make()
        roll(g, (1, 2))
        clock.t += 20
        g.tick()  # no decision: off to auction
        self.assertEqual(g.phase, "auction")
        clock.t += 20
        g.tick()
        self.assertNotIn(3, g.owner)


class RentTests(unittest.TestCase):
    def test_street_set_houses_stations_utilities_mortgage(self):
        g, _ = make()
        a, b = g.order[0], g.order[1]
        give(g, b, 1)
        self.assertEqual(g.rent(1, 7), 2)
        give(g, b, 3)
        self.assertEqual(g.rent(1, 7), 4)  # whole set: double
        g.houses[1] = 3
        self.assertEqual(g.rent(1, 7), 90)
        give(g, b, 5, 15)
        self.assertEqual(g.rent(5, 7), 50)
        give(g, b, 25, 35)
        self.assertEqual(g.rent(35, 7), 200)
        give(g, b, 12)
        self.assertEqual(g.rent(12, 7), 28)
        give(g, b, 28)
        self.assertEqual(g.rent(12, 7), 70)
        # landing pays; a mortgaged one doesn't
        g.mortgaged.add(5)
        g.pos[a] = 2
        roll(g, (1, 2))  # 5: mortgaged station
        self.assertEqual(g.cash[a], 1500)
        g.must_roll, g.phase = True, "roll"
        roll(g, (6, 4))  # 15: station, 4 owned -> $200
        self.assertEqual((g.cash[a], g.cash[b]), (1300, 1700))


class BuildTests(unittest.TestCase):
    def test_build_evenly_hotels_and_selling(self):
        g, _ = make()
        me = g.current
        give(g, me, 6, 8)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "build", "square": 6})  # no set
        give(g, me, 9)
        g.handle(me, {"a": "build", "square": 6})
        with self.assertRaises(GameError):
            g.handle(me, {"a": "build", "square": 6})  # uneven
        for sq in (8, 9):
            g.handle(me, {"a": "build", "square": sq})
        for _ in range(4):
            for sq in (6, 8, 9):
                g.handle(me, {"a": "build", "square": sq})
        self.assertEqual([g.houses[s] for s in (6, 8, 9)], [5, 5, 5])
        self.assertEqual(g._hotels_left(), 9)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "build", "square": 6})  # full
        with self.assertRaises(GameError):
            g.handle(me, {"a": "mortgage", "square": 6})  # buildings
        cash = g.cash[me]
        g.handle(me, {"a": "sell", "square": 9})
        self.assertEqual((g.houses[9], g.cash[me]), (4, cash + 25))
        with self.assertRaises(GameError):
            g.handle(me, {"a": "sell", "square": 9})  # uneven

    def test_house_shortage_mortgage_rules(self):
        g, _ = make()
        me = g.current
        give(g, me, 6, 8, 9)
        g.houses.update({s: 4 for s in (11, 13, 14, 16, 18, 19, 21, 23)})
        for s in (11, 13, 14, 16, 18, 19, 21, 23):
            g.owner[s] = g.order[1]
        self.assertEqual(g._houses_left(), 0)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "build", "square": 6})
        g.handle(me, {"a": "mortgage", "square": 6})
        self.assertEqual(g.cash[me], 1550)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "mortgage", "square": 6})
        g.handle(me, {"a": "unmortgage", "square": 6})
        self.assertEqual(g.cash[me], 1495)  # $50 + 10%
        with self.assertRaises(GameError):
            g.handle(me, {"a": "build", "square": 1})  # not yours
        other = g.order[1]
        with self.assertRaises(GameError):
            g.handle(other, {"a": "mortgage", "square": 11})  # not your turn


class CardTests(unittest.TestCase):
    def deal(self, g, deck, index):
        g.piles[deck].remove(index)
        g.piles[deck].insert(0, index)

    def test_station_double_and_utility_ten(self):
        g, _ = make()
        me, owner = g.order[0], g.order[1]
        give(g, owner, 15, 12)
        self.deal(g, "chance", 3)
        g.pos[me] = 4
        roll(g, (1, 2))  # 7: Surprise -> nearest station (15), double rent: 2 x 25
        self.assertEqual((g.pos[me], g.cash[me]), (15, 1450))
        g.must_roll, g.phase = True, "roll"
        self.deal(g, "chance", 5)
        g.pos[me] = 4
        roll(g, (1, 2), (5, 5))  # 7 -> nearest utility (12), then a fresh roll: 10 x 10
        self.assertEqual((g.pos[me], g.cash[me]), (12, 1350))

    def test_birthday_back_three_repairs(self):
        g, _ = make()
        me = g.current
        self.deal(g, "fund", 8)  # birthday: $10 from every player
        roll(g, (1, 1))  # 2: Community Fund
        self.assertEqual(g.cash[me], 1520)
        self.deal(g, "chance", 8)  # back 3 from 7 -> 4 (Income Tax)
        roll(g, (2, 3))
        self.assertEqual((g.pos[me], g.cash[me]), (4, 1320))
        give(g, me, 6, 8, 9)
        g.houses.update({6: 5, 8: 2, 9: 2})
        g.must_roll, g.phase = True, "roll"
        self.deal(g, "chance", 10)  # $25/house, $100/hotel
        g.pos[me] = 4
        roll(g, (1, 2))
        self.assertEqual(g.cash[me], 1320 - 4 * 25 - 100)

    def test_free_card_is_kept_and_removed_from_the_pile(self):
        g, _ = make()
        me = g.current
        self.deal(g, "fund", 4)
        roll(g, (1, 1))
        self.assertEqual(g.free_cards[me], ["fund:4"])
        self.assertNotIn(4, g.piles["fund"])


class DebtTests(unittest.TestCase):
    def test_raise_money_then_pay(self):
        g, _ = make()
        me, owner = g.order[0], g.order[1]
        give(g, owner, 39)
        g.houses[39] = 5
        give(g, owner, 37)
        give(g, me, 1, 3)
        g.cash[me] = 1990
        g.pos[me] = 36
        roll(g, (1, 2))  # 39 with a hotel: $2000
        self.assertEqual(g.phase, "debt")
        self.assertEqual(g.view_for(me)["debt"]["amount"], 2000)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "pay_debt"})
        with self.assertRaises(GameError):
            g.handle(me, {"a": "build", "square": 1})  # no building while in debt
        g.handle(me, {"a": "mortgage", "square": 1})
        g.handle(me, {"a": "pay_debt"})
        self.assertEqual((g.cash[me], g.cash[owner], g.phase), (20, 3500, "manage"))

    def test_bankrupt_to_a_player_and_to_the_bank(self):
        g, _ = make()
        a, b, c = g.order
        give(g, b, 39)
        g.houses[39] = 5
        give(g, b, 37)
        give(g, a, 1, 3, 5)
        g.houses.update({1: 1, 3: 1})
        g.free_cards[a].append("fund:4")
        g.cash[a] = 100
        g.pos[a] = 36
        roll(g, (1, 2))
        g.handle(a, {"a": "bankrupt"})
        self.assertEqual(g.out, [a])
        self.assertEqual({g.owner[s] for s in (1, 3, 5)}, {b})
        self.assertEqual(g.houses.get(1, 0), 0)
        self.assertEqual(g.cash[b], 1500 + 100 + 50)  # cash + the buildings sold at half
        self.assertEqual(g.free_cards[b], ["fund:4"])
        self.assertNotEqual(g.current, a)
        # c owes the bank and can't pay: properties go back on sale
        give(g, c, 6)
        g.cash[c] = 10
        g.current, g.phase, g.must_roll = c, "roll", True
        g.pos[c] = 1
        roll(g, (1, 2))  # 4: Income Tax $200
        self.assertEqual(g.phase, "debt")
        with self.assertRaises(GameError):
            g.handle(b, {"a": "bankrupt"})  # not b's debt
        g.handle(c, {"a": "bankrupt"})
        self.assertNotIn(6, g.owner)
        self.assertEqual(g.phase, "final")  # one player left
        self.assertEqual(g.scores()[b], g.worth(b))
        self.assertEqual((g.scores()[a], g.scores()[c]), (1, 2))
        self.assertTrue(g.highlights())

    def test_timeout_sells_and_mortgages_for_you(self):
        g, clock = make()
        a, b = g.order[0], g.order[1]
        give(g, b, 39, 37)
        give(g, a, 6, 8, 9)
        g.houses.update({6: 1, 8: 1, 9: 1})
        g.cash[a] = 0
        g.pos[a] = 36
        roll(g, (1, 2))  # $100 (set, no houses: double 50)
        self.assertEqual(g.phase, "debt")
        clock.t += 45
        g.tick()
        self.assertEqual(g.cash[b], 1600)
        self.assertNotIn(a, g.out)
        self.assertEqual(sum(g.houses.get(s, 0) for s in (6, 8, 9)), 0)  # sold $75, then mortgaged one


class TradeTests(unittest.TestCase):
    def test_offer_accept_and_rules(self):
        g, _ = make()
        a, b, c = g.order
        give(g, a, 1)
        give(g, b, 3, 5)
        g.mortgaged.add(5)
        bad = [
            {"to": a, "give": {}, "get": {}},
            {"to": b, "give": {}, "get": {}},
            {"to": b, "give": {"cash": 5000}, "get": {}},
            {"to": b, "give": {"squares": [3]}, "get": {}},
            {"to": b, "give": {"squares": "1"}, "get": {}},
            {"to": b, "give": {"oops": 1}, "get": {}},
            {"to": "zz", "give": {"cash": 1}, "get": {}},
        ]
        for msg in bad:
            with self.assertRaises(GameError, msg=repr(msg)):
                g.handle(a, {"a": "offer", **msg})
        g.handle(
            a, {"a": "offer", "to": b, "give": {"squares": [1], "cash": 100}, "get": {"squares": [3, 5]}}
        )
        tid = g.trades and next(iter(g.trades))
        with self.assertRaises(GameError):
            g.handle(c, {"a": "accept", "trade": tid})
        g.handle(b, {"a": "accept", "trade": tid})
        self.assertEqual((g.owner[1], g.owner[3], g.owner[5]), (b, a, a))
        self.assertEqual(g.cash[a], 1500 - 100 - 10)  # 10% interest on the mortgaged station
        self.assertEqual(g.cash[b], 1600)
        self.assertEqual(g.trades, {})

    def test_buildings_block_and_stale_offers_drop(self):
        g, _ = make()
        a, b, c = g.order
        give(g, a, 1, 3, 6)
        g.houses[3] = 1
        with self.assertRaises(GameError):
            g.handle(a, {"a": "offer", "to": b, "give": {"squares": [1]}, "get": {}})
        g.handle(a, {"a": "offer", "to": b, "give": {"squares": [6]}, "get": {"cash": 50}})
        g.handle(a, {"a": "offer", "to": c, "give": {"squares": [6]}, "get": {"cash": 60}})
        self.assertEqual(len(g.trades), 1)  # a new offer replaces your old one
        tid = next(iter(g.trades))
        g.handle(c, {"a": "reject", "trade": tid})
        self.assertEqual(g.trades, {})
        g.handle(a, {"a": "offer", "to": b, "give": {"squares": [6]}, "get": {"cash": 50}})
        g.handle(b, {"a": "offer", "to": c, "give": {"cash": 1}, "get": {}})
        g.owner[6] = c  # (sold elsewhere)
        tid_b = next(t for t, tr in g.trades.items() if tr["from"] == b)
        g.handle(c, {"a": "accept", "trade": tid_b})
        self.assertEqual(list(g.trades), [])  # a's offer of square 6 no longer adds up


class ClockTests(unittest.TestCase):
    def test_timeouts_keep_the_game_moving(self):
        g, clock = make()
        first = g.current
        clock.t += 30
        g.tick()  # auto-roll
        self.assertIsNotNone(g.dice)
        while g.current == first:
            clock.t += 50
            g.tick()
        self.assertNotEqual(g.current, first)

    def test_party_clock_ends_after_the_turn(self):
        g, clock = make(length="30")
        me = g.current
        clock.t += 31 * 60
        roll(g, (1, 2))
        g.handle(me, {"a": "buy"})
        self.assertFalse(g.finished)
        g.handle(me, {"a": "end"})
        self.assertEqual(g.phase, "final")
        self.assertEqual(g.scores()[me], g.worth(me))
        self.assertEqual(g.worth(me), 1500)  # $60 cash became a $60 street

    def test_call_it_a_night(self):
        g, _ = make(length="0")
        a, b, c = g.order
        g.handle(a, {"a": "call_it"})
        g.handle(b, {"a": "call_it"})
        g.handle(b, {"a": "call_it", "on": False})
        g.handle(c, {"a": "call_it"})
        self.assertFalse(g.finished)
        self.assertEqual(g.view_for(a)["call_it"], sorted([a, c]))
        g.handle(b, {"a": "call_it"})
        self.assertTrue(g.finished)
        self.assertEqual(g.scores(), {p: 1500 for p in g.order})
        with self.assertRaises(GameError):
            g.handle(a, {"a": "roll"})

    def test_no_limit(self):
        g, _ = make(length="0")
        self.assertIsNone(g.ends_at)
        self.assertIsNone(g.view_for("p0")["ends_in"])


class ViewTests(unittest.TestCase):
    def test_views_are_public_and_never_show_the_decks(self):
        g, _ = make(4)
        roll(g, (1, 2))
        for pid in [*g.order, *SPECTATORS]:
            v = g.view_for(pid)
            json.dumps(v)
            self.assertNotIn("piles", v)
            self.assertEqual(v["you"]["playing"], pid in g.order)
        self.assertIn("Surprise", g.peek(g.order[0]) or "")
        with self.assertRaises(GameError):
            g.handle(g.order[1], {"a": "roll"})
        with self.assertRaises(GameError):
            g.handle(g.current, {"a": "teleport"})


if __name__ == "__main__":
    unittest.main()
