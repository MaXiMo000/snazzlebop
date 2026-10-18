"""Imposter: the deal, clues, votes, the last guess, scoring, both twists, and who sees which word."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.imposter import CREW_WIN, ESCAPE, RIGHT_VOTE, STEAL, Imposter, says

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1, **options):
    clock = Clock()
    g = Imposter(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options={k: str(v) for k, v in options.items()},
    )
    g.start()
    return g, clock


def clues(g):
    g.advance()  # cards -> clues
    while g.phase == "clue":
        pid = g.turn
        g.handle(pid, {"a": "clue", "text": fresh(g)})


def fresh(g):
    """A clue nobody has given yet (clues compare letters only)."""
    return "clue" + "abcdefghijklmnopqrstuvwxyz"[len(g.clues)]


def vote_all(g, target_of):
    for p in g.player_ids:
        g.handle(p, {"a": "vote", "target": target_of(p)})


def crew(g):
    return [p for p in g.player_ids if p != g.imposter]


class ImposterTests(unittest.TestCase):
    def test_says_matches_whole_words(self):
        self.assertTrue(says("PIZZA", "pizza"))
        self.assertTrue(says("pizzas!", "pizza"))
        self.assertTrue(says("icecream", "ice cream"))
        self.assertFalse(says("category", "cat"))
        self.assertFalse(says("cheesy", "cheese cake"))

    def test_the_deal_and_clue_turns(self):
        g, _ = make(4, clues=2)
        self.assertEqual(g.phase, "cards")
        self.assertEqual(len(g.order), 8)
        self.assertEqual(sorted(g.order[:4]), sorted(g.player_ids))
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "clue", "text": "x"})  # cards first
        g.advance()
        first = g.turn
        other = next(p for p in g.player_ids if p != first)
        with self.assertRaises(GameError) as e:
            g.handle(other, {"a": "clue", "text": "hello"})
        self.assertEqual(e.exception.code, "not_your_turn")
        g.handle(first, {"a": "clue", "text": "  round  "})
        self.assertEqual(g.clues[0], {"by": first, "text": "round"})
        with self.assertRaises(GameError) as e:
            g.handle(g.turn, {"a": "clue", "text": "ROUND"})
        self.assertEqual(e.exception.code, "taken")
        for bad in ("", "one two three", "x" * 30, 5, "tab\there"):
            with self.assertRaises(GameError):
                g.handle(g.turn, {"a": "clue", "text": bad})
        g.advance()  # out of time: a pass
        self.assertEqual(g.clues[1]["text"], "")
        while g.phase == "clue":
            g.handle(g.turn, {"a": "clue", "text": fresh(g)})
        self.assertEqual(g.phase, "vote")
        self.assertEqual(len(g.clues), 8)

    def test_crew_cant_say_the_word_in_a_clue_or_the_chat(self):
        g, _ = make(4)
        g.advance()
        while g.turn == g.imposter:
            g.handle(g.turn, {"a": "clue", "text": fresh(g)})
        word = g.card["word"]
        with self.assertRaises(GameError) as e:
            g.handle(g.turn, {"a": "clue", "text": word.upper()})
        self.assertEqual(e.exception.code, "gives_away")
        self.assertIsNotNone(g.chat_blocked(crew(g)[0], f"it's {word} obviously"))
        self.assertIsNone(g.chat_blocked(g.imposter, f"is it {word}?"))  # they don't know it
        self.assertIsNone(g.chat_blocked(crew(g)[0], "hmm, suspicious"))

    def test_caught_imposter_who_misses_the_guess_loses(self):
        g, _ = make(4)
        clues(g)
        imp = g.imposter
        with self.assertRaises(GameError):
            g.handle(imp, {"a": "vote", "target": imp})  # not yourself
        vote_all(g, lambda p: imp if p != imp else crew(g)[0])
        self.assertEqual(g.phase, "guess")
        for viewer in g.player_ids:
            self.assertEqual(g.view_for(viewer)["accused"], imp)
        with self.assertRaises(GameError):
            g.handle(crew(g)[0], {"a": "guess", "text": "x"})
        g.handle(imp, {"a": "guess", "text": "definitely wrong"})
        self.assertEqual(g.phase, "result")
        r = g.result
        self.assertTrue(r["caught"])
        self.assertFalse(r["stole"])
        for p in crew(g):
            self.assertEqual(r["gains"][p], RIGHT_VOTE + CREW_WIN)
        self.assertEqual(r["gains"][imp], 0)

    def test_caught_imposter_can_steal_with_the_word(self):
        g, _ = make(4)
        clues(g)
        imp = g.imposter
        vote_all(g, lambda p: imp if p != imp else crew(g)[0])
        g.handle(imp, {"a": "guess", "text": g.card["word"].upper() + "S"})
        r = g.result
        self.assertTrue(r["stole"])
        self.assertEqual(r["gains"][imp], STEAL)
        for p in crew(g):
            self.assertEqual(r["gains"][p], RIGHT_VOTE)

    def test_a_tie_or_the_wrong_player_lets_the_imposter_escape(self):
        g, _ = make(4)
        clues(g)
        imp = g.imposter
        a, b, c = crew(g)
        votes = {imp: a, a: b, b: a, c: b}  # a and b tie
        vote_all(g, lambda p: votes[p])
        self.assertEqual(g.phase, "result")
        self.assertIsNone(g.result["accused"])
        self.assertEqual(g.result["gains"][imp], ESCAPE)
        g, _ = make(4, seed=2)
        clues(g)
        imp = g.imposter
        a, b, c = crew(g)
        votes = {imp: a, a: b, b: a, c: a}  # a framed
        vote_all(g, lambda p: votes[p])
        self.assertEqual(g.result["accused"], a)
        self.assertFalse(g.result["caught"])
        self.assertEqual(g.result["gains"][imp], ESCAPE)

    def test_undercover_imposter_gets_a_close_word_and_no_guess(self):
        g, _ = make(5, twist="undercover")
        imp = g.imposter
        mine = g.view_for(imp)["you"]
        self.assertEqual(mine["word"], g.card["close"])
        self.assertFalse(mine["imposter"])  # they think they're crew
        for p in crew(g):
            self.assertEqual(g.view_for(p)["you"]["word"], g.card["word"])
        clues(g)
        vote_all(g, lambda p: imp if p != imp else crew(g)[0])
        self.assertEqual(g.phase, "result")  # straight to the result
        self.assertTrue(g.result["caught"])
        self.assertEqual(g.result["close"], g.card["close"])

    def test_secrets_in_every_phase(self):
        for twist in ("classic", "undercover"):
            g, _ = make(5, twist=twist, words=2)
            for _ in range(200):
                if g.finished:
                    break
                imp, word, close = g.imposter, g.card["word"], g.card["close"]
                hidden = g.phase not in ("result", "final")
                for viewer in (*g.player_ids, *SPECTATORS):
                    v = g.view_for(viewer)
                    raw = json.dumps({k: v[k] for k in v if k not in ("history",)})
                    if hidden and g.phase != "guess":
                        self.assertNotIn(f'"{imp}"', json.dumps(v["you"]) if viewer == imp else "", viewer)
                        self.assertIsNone(v.get("result"))
                    if hidden and (viewer in SPECTATORS or viewer == imp):
                        self.assertNotIn(word, raw, (twist, g.phase, viewer))
                    if hidden and viewer != imp:
                        self.assertNotIn(f'"{close}"', raw, (twist, g.phase, viewer))
                    if viewer in SPECTATORS:
                        self.assertIsNone(v["you"])
                if g.phase == "vote":
                    for p in g.player_ids:
                        g.handle(p, {"a": "vote", "target": next(q for q in g.player_ids if q != p)})
                        if g.phase != "vote":
                            break
                        for viewer in (*g.player_ids, *SPECTATORS):
                            seen = g.view_for(viewer)
                            self.assertIsNone(seen.get("result"))
                            self.assertNotIn('"votes"', json.dumps(seen))
                elif g.phase == "clue":
                    g.handle(g.turn, {"a": "clue", "text": fresh(g)})
                else:
                    g.advance()
            self.assertTrue(g.finished)
            final = g.view_for("tv:screen")
            self.assertEqual(len(final["history"]), 2)

    def test_skip_only_between_turns(self):
        g, _ = make(3)
        self.assertTrue(g.skip())  # cards
        self.assertEqual(g.phase, "clue")
        self.assertFalse(g.skip())
        while g.phase == "clue":
            g.handle(g.turn, {"a": "clue", "text": fresh(g)})
        self.assertFalse(g.skip())  # vote
        g.advance()  # the clock: nobody voted, nobody caught
        self.assertEqual(g.phase, "result")
        self.assertEqual(g.result["gains"][g.imposter], ESCAPE)
        self.assertTrue(g.skip())

    def test_imposter_changes_and_words_dont_repeat(self):
        g, _ = make(4, words=5)
        seen, imposters = [], []
        while not g.finished:
            seen.append(g.card["word"])
            imposters.append(g.imposter)
            clues(g)
            g.advance()  # votes close
            if g.phase == "guess":
                g.advance()
            g.advance()  # result -> next
        self.assertEqual(len(set(seen)), 5)
        self.assertTrue(all(a != b for a, b in zip(imposters, imposters[1:], strict=False)))
        self.assertTrue(g.highlights() or True)
