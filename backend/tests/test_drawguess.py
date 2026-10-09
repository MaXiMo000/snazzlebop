"""Draw & Guess: turns, guessing and scoring, hints, secrecy, the ink log and the hub's ink relay."""

from __future__ import annotations

import asyncio
import json
import random
import unittest

from app.games import GameError, Player
from app.games.content import DRAW_WORDS
from app.games.drawguess import DrawGuess, one_off, squash
from app.games.ink import MAX_POINTS_PER_OP, InkLog

from .test_rooms import FakeConn, HubHarness

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = DrawGuess(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def drawing(g, i=0):
    """Pick choice i; return the drawer and the guessers."""
    g.handle(g.drawer, {"a": "pick", "i": i})
    return g.drawer, [p for p in g.player_ids if p != g.drawer]


class WordTests(unittest.TestCase):
    def test_pool(self):
        self.assertGreater(len(DRAW_WORDS), 300)
        self.assertEqual(len(DRAW_WORDS), len(set(DRAW_WORDS)))
        for w in DRAW_WORDS:
            self.assertTrue(w == w.lower() and w.replace(" ", "").isalpha() and len(w) <= 20, w)

    def test_matching(self):
        self.assertEqual(squash(" Hot-Dog! "), "hotdog")
        self.assertTrue(one_off("pizz", "pizza"))
        self.assertTrue(one_off("pizzo", "pizza"))
        self.assertTrue(one_off("pizzaa", "pizza"))
        self.assertFalse(one_off("pizza", "pizza"))
        self.assertFalse(one_off("pazzo", "pizza"))


class TurnTests(unittest.TestCase):
    def test_choose_then_guess_and_score(self):
        g, clock = make(3)
        self.assertEqual(g.phase, "choose")
        drawer = g.drawer
        other = next(p for p in g.player_ids if p != drawer)
        with self.assertRaises(GameError):
            g.handle(other, {"a": "pick", "i": 0})
        for bad in (3, -1, "0", True, None):
            with self.assertRaises(GameError):
                g.handle(drawer, {"a": "pick", "i": bad})
        choice = g.choices[1]
        _, guessers = drawing(g, 1)
        self.assertEqual((g.phase, g.word), ("draw", choice))
        with self.assertRaises(GameError):
            g.handle(drawer, {"a": "guess", "text": choice})  # the artist can't guess
        g.handle(guessers[0], {"a": "guess", "text": "definitely wrong"})
        self.assertEqual(g.feed[-1]["text"], "definitely wrong")
        clock.t += g.draw_seconds / 2
        g.handle(guessers[0], {"a": "guess", "text": choice.upper()})
        self.assertEqual(g.gained[guessers[0]], 100 + 150)
        self.assertEqual(g.gained[drawer], 75)
        self.assertEqual(g.feed[-1], {"by": guessers[0], "ok": True})  # the word itself never appears
        with self.assertRaises(GameError):
            g.handle(guessers[0], {"a": "guess", "text": "again"})
        g.handle(guessers[1], {"a": "guess", "text": choice})
        self.assertEqual(g.phase, "reveal")  # everyone got it: the turn ends early
        self.assertEqual(g.scores()[drawer], 150)

    def test_guess_validation(self):
        g, _ = make(2)
        _, (guesser,) = drawing(g)
        for bad in (None, 5, "", "   ", "x" * 33, "a\nb", ["pizza"]):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle(guesser, {"a": "guess", "text": bad})
        with self.assertRaises(GameError):
            g.handle(guesser, {"a": "dance"})

    def test_close_guess_is_told_only_to_the_guesser(self):
        g, _ = make(3)
        g.choices = ["pizza", "cat", "dog"]
        drawer, (a, b) = drawing(g, 0)
        g.handle(a, {"a": "guess", "text": "pizzo"})
        self.assertTrue(g.view_for(a)["feed"][-1]["close"])
        for pid in (b, drawer, *SPECTATORS):
            self.assertNotIn("close", g.view_for(pid)["feed"][-1])

    def test_timeouts_rounds_and_final(self):
        g, clock = make(2, turns="1")
        g.tick()
        clock.t += 15
        g.tick()  # nobody picked: a random choice
        self.assertEqual(g.phase, "draw")
        self.assertIn(g.word, g.choices)
        clock.t += g.draw_seconds
        g.tick()
        self.assertEqual(g.phase, "reveal")
        self.assertEqual(g.history[-1]["guessed"], [])
        g.advance()
        self.assertEqual((g.phase, g.round), ("choose", 0))  # the second player's turn, same round
        g.advance()
        g.advance()
        g.advance()
        self.assertEqual(g.phase, "final")
        self.assertTrue(g.finished)
        self.assertEqual(len(g.history), 2)
        self.assertEqual({h["drawer"] for h in g.history}, set(g.player_ids))  # everyone drew once
        self.assertIsNone(g.view_for("p0")["drawer"])
        self.assertTrue(g.highlights())
        json.dumps(g.view_for("p0"))

    def test_hints_reveal_letters_but_never_the_word(self):
        g, clock = make(2, time="80")
        g.choices = ["sunflower", "x", "y"]
        _, (guesser,) = drawing(g, 0)
        letters = lambda: [c for c in g.view_for(guesser)["pattern"] if c]  # noqa: E731
        self.assertEqual(g.view_for(guesser)["pattern"], [""] * 9)
        clock.t += 41
        g.tick()
        self.assertEqual(len(letters()), 1)
        clock.t += 20
        g.tick()
        self.assertEqual(len(letters()), 2)
        g.tick()
        self.assertEqual(len(letters()), 2)
        g.choices = ["cat"]
        g2, c2 = make(2)
        g2.choices = ["hot dog", "a", "b"]
        _, (other,) = drawing(g2, 0)
        self.assertEqual(g2.view_for(other)["pattern"], ["", "", "", " ", "", "", ""])

    def test_secrecy_in_every_phase(self):
        g, clock = make(4, turns="1")
        while not g.finished:
            drawer = g.drawer
            if g.phase == "choose":
                for pid in [*g.player_ids, *SPECTATORS]:
                    v = g.view_for(pid)
                    blob = json.dumps(v)
                    if pid == drawer:
                        self.assertEqual(v["choices"], g.choices)
                    else:
                        self.assertIsNone(v["choices"])
                        for w in g.choices:
                            self.assertNotIn(f'"{w}"', blob, pid)
                drawing(g)
            elif g.phase == "draw":
                first = next(p for p in g.player_ids if p != drawer)
                g.handle(first, {"a": "guess", "text": g.word})
                for pid in [*g.player_ids, *SPECTATORS]:
                    v = g.view_for(pid)
                    knows = pid in (drawer, first)
                    self.assertEqual(v["word"] == g.word, knows, pid)
                    if not knows:
                        self.assertNotIn(f'"{g.word}"', json.dumps(v), pid)
                        self.assertTrue(all(c in ("", " ") for c in v["pattern"]))
                clock.t += g.draw_seconds
                g.tick()
            else:
                for pid in [*g.player_ids, *SPECTATORS]:
                    self.assertEqual(g.view_for(pid)["word"], g.word)
                g.advance()
        for pid in [*g.player_ids, *SPECTATORS]:
            v = g.view_for(pid)
            self.assertEqual(v["phase"], "final")
            self.assertEqual(len(v["history"]), 4)

    def test_peek(self):
        g, _ = make(3)
        self.assertIsNone(g.peek(g.drawer))
        drawer, (a, _b) = drawing(g)
        self.assertIn(g.word[0].upper(), g.peek(a))
        self.assertIsNone(g.peek(drawer))


class InkTests(unittest.TestCase):
    def test_ops_and_validation(self):
        ink = InkLog()
        ink.add({"op": "line", "c": 0, "w": 1, "p": [0, 0, 800, 600]})
        ink.add({"op": "more", "p": [10, 10]})
        ink.add({"op": "undo"})
        self.assertEqual(ink.view(), {"id": ink.id, "count": 3})
        with self.assertRaises(GameError):
            ink.add({"op": "more", "p": [1, 1]})  # undo closed the stroke
        bad = [
            {"op": "line", "c": 99, "w": 0, "p": [1, 1]},
            {"op": "line", "c": True, "w": 0, "p": [1, 1]},
            {"op": "line", "c": 0, "w": 9, "p": [1, 1]},
            {"op": "line", "c": 0, "w": 0, "p": [1]},
            {"op": "line", "c": 0, "w": 0, "p": [801, 1]},
            {"op": "line", "c": 0, "w": 0, "p": [1, 601]},
            {"op": "line", "c": 0, "w": 0, "p": [1.5, 1]},
            {"op": "line", "c": 0, "w": 0, "p": "1,1"},
            {"op": "line", "c": 0, "w": 0, "p": [1, 1] * (MAX_POINTS_PER_OP // 2 + 1)},
            {"op": "fill"},
            {},
        ]
        for msg in bad:
            with self.assertRaises(GameError, msg=repr(msg)):
                ink.add(msg)
        self.assertEqual(len(ink.ops), 3)

    def test_only_the_artist_draws_and_only_while_drawing(self):
        g, _ = make(3)
        stroke = {"op": "line", "c": 0, "w": 0, "p": [1, 1, 2, 2]}
        with self.assertRaises(GameError):
            g.ink(g.drawer, stroke)  # still choosing
        drawer, (a, _b) = drawing(g)
        with self.assertRaises(GameError):
            g.ink(a, stroke)
        self.assertEqual(g.ink(drawer, stroke).view()["count"], 1)
        self.assertEqual(g.view_for("tv:screen")["ink"], g.canvas.view())


class InkRelayTests(HubHarness):
    async def test_strokes_reach_everyone_else_in_order_and_sync_on_request(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        _, _tv = hub.issue_tv(room.code)
        vid = next(iter(room.viewers))
        screen = FakeConn()
        await hub.connect(room, vid, screen)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "drawguess"})
        g = room.game
        drawer = g.drawer
        guesser = next(p for p in g.player_ids if p != drawer)
        await hub.handle_message(room, guesser, conns[guesser], {"t": "ink", "op": "clear"})
        self.assertEqual(conns[guesser].errors(), ["wrong_phase"])  # the artist is still choosing
        await hub.handle_message(room, drawer, conns[drawer], {"t": "act", "a": "pick", "i": 0})
        await hub.handle_message(room, guesser, conns[guesser], {"t": "ink", "op": "clear"})
        self.assertIn("not_your_turn", conns[guesser].errors())
        await hub.handle_message(
            room, drawer, conns[drawer], {"t": "ink", "op": "line", "c": 1, "w": 2, "p": [5, 5, 6, 6]}
        )
        await hub.handle_message(room, drawer, conns[drawer], {"t": "ink", "op": "more", "p": [7, 7]})
        await asyncio.sleep(0.05)
        ink = lambda c: [m for m in c.sent if m["t"] == "ink"]  # noqa: E731
        for c in (conns[guesser], screen):
            ops = [op for m in ink(c) for op in m["ops"]]
            self.assertEqual([op["op"] for op in ops], ["line", "more"])
            self.assertEqual(ink(c)[0]["n"], 0)
            self.assertEqual(ink(c)[0]["id"], g.canvas.id)
        self.assertEqual(ink(conns[drawer]), [])  # the artist already has it
        # Late screen: asks for the whole drawing.
        await hub.handle_message(room, vid, screen, {"t": "inksync"})
        await asyncio.sleep(0.05)
        last = ink(screen)[-1]
        self.assertEqual((last["n"], len(last["ops"])), (0, 2))
        # Strokes don't send snapshots; the next one carries the new count (so gaps can be noticed).
        self.assertEqual(screen.last["game"]["ink"]["count"], 0)
        self.assertEqual(hub.view_for(room, vid)["game"]["ink"], {"id": g.canvas.id, "count": 2})

    def test_frames_batch_and_resync(self):
        items = [{"id": "a", "n": 0, "op": 1}, {"id": "a", "n": 1, "op": 2}, {"id": "b", "n": 0, "op": 3}]
        frames = type(self.make_hub())._ink_frames([*items, {"resync": True}])
        self.assertEqual(
            frames,
            [
                {"t": "ink", "id": "a", "n": 0, "ops": [1, 2]},
                {"t": "ink", "id": "b", "n": 0, "ops": [3]},
                {"t": "ink", "resync": True},
            ],
        )


if __name__ == "__main__":
    unittest.main()
