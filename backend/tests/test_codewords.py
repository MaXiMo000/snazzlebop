"""Codewords: setup, the key, clue rules, guessing, turns, endings, secrecy."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.codewords import WIN_POINTS, Codewords, other

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1, **opts):
    clock = Clock()
    g = Codewords(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def started(n=4, seed=1):
    g, clock = make(n, seed)
    g.advance()  # teams -> clue
    return g, clock


def spy(g, team=None):
    return g.spymasters[team or g.turn]


def guesser(g, team=None):
    t = team or g.turn
    return next(p for p, v in g.teams.items() if v == t and p != g.spymasters[t])


def find(g, color, start=0):
    return next(i for i in range(start, 25) if g.key[i] == color and not g.revealed[i])


def safe_clue(g):
    return next(
        w for w in ("ZEBRAFISH", "QUOKKA", "XYLOPHONIST") if all(w not in x and x not in w for x in g.words)
    )


class SetupTests(unittest.TestCase):
    def test_starts_with_balanced_teams_and_a_spymaster_each(self):
        g, _ = make(5)
        self.assertEqual(g.phase, "teams")
        counts = [list(g.teams.values()).count(t) for t in ("red", "blue")]
        self.assertEqual(sorted(counts), [2, 3])
        self.assertTrue(g._valid_teams())
        self.assertFalse(Codewords.SHOW)

    def test_switching_teams_and_claiming_spymaster(self):
        g, _ = make(4)
        red_spy = g.spymasters["red"]
        g.handle(red_spy, {"a": "team", "team": "blue"})
        self.assertIsNone(g.spymasters["red"])  # left their post
        self.assertFalse(g.view_for("p0")["valid_teams"])
        newbie = next(p for p, v in g.teams.items() if v == "red")
        g.handle(newbie, {"a": "spymaster"})
        self.assertEqual(g.spymasters["red"], newbie)
        for bad in ("green", None, 1):
            with self.assertRaises(GameError):
                g.handle("p0", {"a": "team", "team": bad})

    def test_an_unplayable_setup_is_fixed_at_the_start(self):
        g, _ = make(4)
        for p in g.player_ids:
            g.handle(p, {"a": "team", "team": "red"})
        g.advance()
        self.assertTrue(g._valid_teams())
        self.assertEqual(g.phase, "clue")

    def test_the_deal(self):
        g, _ = started()
        self.assertEqual(len(set(g.words)), 25)
        first = g.turn
        self.assertEqual(g.key.count(first), 9)
        self.assertEqual(g.key.count(other(first)), 8)
        self.assertEqual((g.key.count("neutral"), g.key.count("assassin")), (7, 1))
        self.assertEqual(g.view_for("tv:x")["starting"], first)


class SecrecyTests(unittest.TestCase):
    def test_only_spymasters_see_the_key(self):
        g, _ = started(6)
        for p in g.player_ids:
            colors = [c["color"] for c in g.view_for(p)["board"]]
            if p in g.spymasters.values():
                self.assertEqual(colors, g.key)
                self.assertTrue(g.view_for(p)["you"]["spymaster"])
            else:
                self.assertEqual(colors, [None] * 25)
        for viewer in SPECTATORS:
            view = g.view_for(viewer)
            self.assertEqual([c["color"] for c in view["board"]], [None] * 25)
            self.assertNotIn("assassin", json.dumps(view))

    def test_revealed_words_are_public_and_the_end_shows_everything(self):
        g, _ = started()
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 2})
        i = find(g, "neutral")
        g.handle(guesser(g), {"a": "reveal", "card": i})
        self.assertEqual(g.view_for("tv:x")["board"][i]["color"], "neutral")
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 1})
        g.handle(guesser(g), {"a": "reveal", "card": g.key.index("assassin")})
        self.assertEqual([c["color"] for c in g.view_for("tv:x")["board"]], g.key)


class ClueTests(unittest.TestCase):
    def test_clue_rules(self):
        g, _ = started()
        board_word = g.words[0]
        with self.assertRaises(GameError):
            g.handle(guesser(g), {"a": "clue", "word": "OCEAN", "count": 1})  # not the spymaster
        with self.assertRaises(GameError):
            g.handle(spy(g, other(g.turn)), {"a": "clue", "word": "OCEAN", "count": 1})  # wrong team
        for word in (
            board_word,
            board_word.lower(),
            board_word + "S",
            "TWO WORDS",
            "R2D2",
            "",
            "A" * 21,
            5,
            None,
        ):
            with self.assertRaises(GameError, msg=repr(word)):
                g.handle(spy(g), {"a": "clue", "word": word, "count": 1})
        for count in (-1, 10, True, "2", None):
            with self.assertRaises(GameError, msg=repr(count)):
                g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": count})
        g.handle(spy(g), {"a": "clue", "word": " " + safe_clue(g).lower() + " ", "count": 2})
        self.assertEqual(g.clue["word"], safe_clue(g))
        self.assertEqual((g.phase, g.guesses_left), ("guess", 3))

    def test_zero_means_unlimited_guesses(self):
        g, _ = started()
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 0})
        self.assertIsNone(g.guesses_left)
        team = g.turn
        for _ in range(5):
            g.handle(guesser(g), {"a": "reveal", "card": find(g, team)})
        self.assertEqual(g.turn, team)


class GuessTests(unittest.TestCase):
    def test_own_words_continue_until_the_number_plus_one(self):
        g, _ = started()
        team = g.turn
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 1})
        g.handle(guesser(g), {"a": "reveal", "card": find(g, team)})
        self.assertEqual((g.turn, g.guesses_left), (team, 1))
        g.handle(guesser(g), {"a": "reveal", "card": find(g, team)})
        self.assertEqual((g.turn, g.phase), (other(team), "clue"))  # the bonus guess used, turn over

    def test_a_bystander_ends_the_turn_and_the_other_teams_word_helps_them(self):
        g, _ = started()
        team = g.turn
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 3})
        before = g.left(other(team))
        g.handle(guesser(g), {"a": "reveal", "card": find(g, other(team))})
        self.assertEqual(g.left(other(team)), before - 1)
        self.assertEqual(g.turn, other(team))
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 3})
        g.handle(guesser(g), {"a": "reveal", "card": find(g, "neutral")})
        self.assertEqual(g.turn, team)

    def test_only_the_team_on_turn_guesses_and_never_the_spymaster(self):
        g, _ = started()
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 2})
        with self.assertRaises(GameError):
            g.handle(spy(g), {"a": "reveal", "card": 0})
        with self.assertRaises(GameError):
            g.handle(guesser(g, other(g.turn)), {"a": "reveal", "card": 0})
        for bad in (-1, 25, "3", True):
            with self.assertRaises(GameError):
                g.handle(guesser(g), {"a": "reveal", "card": bad})

    def test_pass_needs_a_guess_first(self):
        g, _ = started()
        team = g.turn
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 2})
        with self.assertRaises(GameError):
            g.handle(guesser(g), {"a": "pass"})
        g.handle(guesser(g), {"a": "reveal", "card": find(g, team)})
        g.handle(guesser(g), {"a": "pass"})
        self.assertEqual(g.turn, other(team))

    def test_marks_toggle_and_clear_on_reveal(self):
        g, _ = started(6)
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 2})
        me = guesser(g)
        i = find(g, g.turn)
        g.handle(me, {"a": "mark", "card": i})
        self.assertEqual(g.view_for("tv:x")["board"][i]["marks"], [me])
        g.handle(me, {"a": "mark", "card": i})
        self.assertEqual(g.view_for("tv:x")["board"][i]["marks"], [])
        g.handle(me, {"a": "mark", "card": i})
        g.handle(me, {"a": "reveal", "card": i})
        self.assertNotIn(i, g.marks)
        with self.assertRaises(GameError):
            g.handle(me, {"a": "mark", "card": i})  # already revealed


class EndingTests(unittest.TestCase):
    def test_the_assassin_loses_on_the_spot(self):
        g, _ = started()
        team = g.turn
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 2})
        g.handle(guesser(g), {"a": "reveal", "card": g.key.index("assassin")})
        self.assertTrue(g.finished)
        self.assertEqual((g.winner, g.how), (other(team), "assassin"))
        for p, t in g.teams.items():
            self.assertEqual(g.scores()[p], WIN_POINTS if t == other(team) else 0)
        self.assertIn("Assassinated", [h["title"] for h in g.highlights()])

    def test_revealing_all_your_words_wins(self):
        g, _ = started()
        team = g.turn
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 0})
        for _ in range(9):
            g.handle(guesser(g), {"a": "reveal", "card": find(g, team)})
        self.assertEqual((g.winner, g.how), (team, "words"))
        self.assertIn("Mind meld", [h["title"] for h in g.highlights()])

    def test_the_other_team_can_win_on_your_turn(self):
        g, _ = started()
        team = g.turn
        rival = other(team)
        for i in range(25):
            if g.key[i] == rival:
                g.revealed[i] = True
        i = next(i for i in range(25) if g.key[i] == rival)
        g.revealed[i] = False  # one rival word left
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 1})
        g.handle(guesser(g), {"a": "reveal", "card": i})
        self.assertEqual(g.winner, rival)

    def test_timeouts_pass_the_turn(self):
        g, clock = started()
        team = g.turn
        clock.t += g.timings["clue"] + 1
        g.tick()
        self.assertEqual((g.turn, g.phase), (other(team), "clue"))
        g.handle(spy(g), {"a": "clue", "word": safe_clue(g), "count": 1})
        clock.t += g.timings["guess"] + 1
        g.tick()
        self.assertEqual(g.turn, team)

    def test_speedy_pace(self):
        g, _ = make(4, pace="speedy")
        self.assertEqual((g.timings["clue"], g.timings["guess"]), (75.0, 90.0))


if __name__ == "__main__":
    unittest.main()
