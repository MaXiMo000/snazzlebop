"""Trivia Tonight: the question bank, five styles, timers, scoring and secrecy in every phase."""

from __future__ import annotations

import json
import random
import unittest

from app.contentgen import v_trivia
from app.games import GameError, Player
from app.games.trivia import LIVES, TriviaTonight
from app.games.trivia_bank import CATEGORIES, TRIVIA, parse, question_key

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = TriviaTonight(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def right(g):
    return g.choices.index(TRIVIA[g.qi]["a"])


def wrong(g):
    return (right(g) + 1) % len(g.choices)


def secret_free(g, pid):
    """What another screen must never hold before the reveal: the answer and anyone else's choice."""
    blob = json.dumps(g.view_for(pid))
    q = TRIVIA[g.qi] if g.qi is not None else None
    return q is None or f'"{q["a"]}"' not in blob.replace(json.dumps(g.choices), "")


class BankTests(unittest.TestCase):
    def test_bank_is_big_valid_and_unique(self):
        self.assertGreater(len(TRIVIA), 1200)
        self.assertEqual({q["cat"] for q in TRIVIA}, set(CATEGORIES))
        keys = [question_key(q["q"]) for q in TRIVIA]
        self.assertEqual(len(keys), len(set(keys)))
        for q in TRIVIA:
            self.assertIn(q["level"], (1, 2, 3))
            self.assertIn(len(q["wrong"]), (1, 3))
            self.assertNotIn(q["a"], q["wrong"])
            self.assertLessEqual(len(q["q"]), 120)
            self.assertTrue(all(len(c) <= 40 for c in [q["a"], *q["wrong"]]))
        for cat in CATEGORIES:  # every category can carry a 20-question game on its own
            self.assertGreaterEqual(sum(q["cat"] == cat for q in TRIVIA), 50)

    def test_parser_rejects_bad_lines(self):
        for bad in (
            "1|No category|a|b|c|d",
            "[nope]\n1|Q?|a|b|c|d",
            "[general]\n4|Q?|a|b|c|d",
            "[general]\n1|Q?|a|a|c|d",
            "[general]\n1|Q?|a|b",
            "[general]\n1|Q?|Maybe",
            "[general]\n1|Same?|a|b|c|d\n2|same|e|f|g|h",
        ):
            with self.assertRaises(ValueError, msg=bad):
                parse(bad)
        self.assertEqual(parse("[space]\n2|The Sun is a star.|True")[0]["wrong"], ["False"])

    def test_generated_questions_are_validated(self):
        ok = {"cat": "space", "level": 2, "q": "Which planet has a moon called Triton?", "a": "Neptune"}
        self.assertIsNotNone(v_trivia({**ok, "wrong": ["Uranus", "Saturn", "Mars"]}))
        for bad in (
            {**ok, "wrong": ["Uranus", "Saturn"]},
            {**ok, "wrong": ["Neptune", "Saturn", "Mars"]},
            {**ok, "cat": "gossip", "wrong": ["Uranus", "Saturn", "Mars"]},
            {**ok, "level": True, "wrong": ["Uranus", "Saturn", "Mars"]},
            {**ok, "q": "Visit www.example.com now?", "wrong": ["Uranus", "Saturn", "Mars"]},
            {**ok, "q": "No question mark here", "wrong": ["Uranus", "Saturn", "Mars"]},
        ):
            self.assertIsNone(v_trivia(bad), bad)


class ClassicTests(unittest.TestCase):
    def test_speed_and_streak_scoring(self):
        g, clock = make(3, questions="5")
        self.assertEqual(g.phase, "question")
        gains = []
        for _ in range(4):
            clock.t += 1  # p0 answers 1 s in: right, p1 at the buzzer: right, p2 wrong
            g.handle("p0", {"a": "answer", "choice": right(g)})
            clock.t += 18.99
            g.handle("p1", {"a": "answer", "choice": right(g)})
            g.handle("p2", {"a": "answer", "choice": wrong(g)})
            self.assertEqual(g.phase, "reveal")  # everyone answered: no waiting
            gains.append(dict(g.result["gains"]))
            self.assertEqual(g.result["first"], "p0")
            g.advance()
        self.assertEqual(gains[0]["p0"], 500 + 480)  # 95% of the speed bonus, to the nearest 10
        self.assertEqual(gains[0]["p1"], 500)
        self.assertEqual(gains[0]["p2"], 0)
        self.assertEqual([x["p0"] - 980 for x in gains], [0, 0, 100, 200])  # streak from the 3rd in a row
        self.assertEqual(g.streak["p2"], 0)

    def test_one_locked_answer_and_input_checks(self):
        g, _ = make(2)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "answer", "choice": 4})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "answer", "choice": True})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "answer", "choice": "1"})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "nope"})
        with self.assertRaises(GameError):
            g.handle("stranger", {"a": "answer", "choice": 0})
        g.handle("p0", {"a": "answer", "choice": 0})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "answer", "choice": 1})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "wager", "amount": 10})

    def test_clock_ends_the_question_and_host_cannot_skip_it(self):
        g, clock = make(2, timer="15")
        g.skip()  # a host skip mid-question does nothing: the clock ends it
        self.assertEqual(g.phase, "question")
        g.handle("p0", {"a": "answer", "choice": right(g)})
        clock.t += 15
        g.tick()
        self.assertEqual(g.phase, "reveal")
        self.assertNotIn("p1", g.result["picks"])
        self.assertEqual(g.result["gains"]["p1"], 0)
        clock.t += 9
        g.tick()
        self.assertEqual((g.phase, g.round), ("question", 1))

    def test_full_game_ends_and_no_question_repeats(self):
        g, clock = make(2, questions="20", topic="tech", level="easy")
        seen = []
        while not g.finished:
            if g.phase == "question":
                seen.append(g.qi)
            clock.t += 30
            g.tick()
        self.assertEqual(len(seen), 20)
        self.assertEqual(len(set(seen)), 20)  # only 9 easy tech questions: harder ones fill in, no repeats
        self.assertTrue(all(TRIVIA[i]["cat"] == "tech" for i in seen))
        self.assertEqual(g.phase, "final")
        self.assertEqual(len(g.view_for("p0")["history"]), 20)

    def test_ramp_gets_harder_and_mix_varies(self):
        g, clock = make(2, questions="10")
        levels, cats = [], []
        while not g.finished:
            if g.phase == "question":
                levels.append(TRIVIA[g.qi]["level"])
                cats.append(g.cat)
            clock.t += 30
            g.tick()
        self.assertEqual(levels, sorted(levels))
        self.assertEqual((levels[0], levels[-1]), (1, 3))
        self.assertGreater(len(set(cats)), 4)
        self.assertTrue(all(a != b for a, b in zip(cats, cats[1:], strict=False)))

    def test_new_games_in_a_room_get_fresh_questions(self):
        decks = {}
        asked = []
        for seed in range(3):
            clock = Clock()
            g = TriviaTonight(
                [Player("p0", "A")],
                rng=random.Random(seed),
                clock=clock,
                decks=decks,
                options={"topic": "space"},
            )
            g.start()
            while not g.finished:
                if g.phase == "question":
                    asked.append(g.qi)
                clock.t += 30
                g.tick()
        self.assertEqual(len(asked), len(set(asked)))  # 30 space questions, none seen twice in the room


class StyleTests(unittest.TestCase):
    def test_fastest_finger(self):
        g, clock = make(3, style="fastest")
        clock.t += 2
        g.handle("p1", {"a": "answer", "choice": wrong(g)})
        clock.t += 1
        g.handle("p2", {"a": "answer", "choice": right(g)})
        clock.t += 1
        g.handle("p0", {"a": "answer", "choice": right(g)})
        self.assertEqual(g.result["gains"], {"p0": 250, "p1": -250, "p2": 1000})
        self.assertEqual(g.result["first"], "p2")

    def test_survival_lives_and_last_one_standing(self):
        g, clock = make(3, style="survival")
        self.assertIsNone(g.view_for("p0")["rounds"])
        # p0 always right, p1 always wrong, p2 never answers
        while not g.finished:
            if g.phase == "question":
                if g.alive("p0"):
                    g.handle("p0", {"a": "answer", "choice": right(g)})
                if g.alive("p1"):
                    g.handle("p1", {"a": "answer", "choice": wrong(g)})
                clock.t += 30
                g.tick()
                if g.phase == "reveal" and g.round == 0:
                    self.assertEqual(g.lives, {"p0": LIVES, "p1": LIVES - 1, "p2": LIVES - 1})
            else:
                clock.t += 30
                g.tick()
        self.assertEqual(g.round + 1, LIVES)  # out on the third question
        self.assertEqual(sorted(g.out_order), ["p1", "p2"])
        self.assertEqual(g.round_scores["p0"], 100 * LIVES + 500)
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "answer", "choice": 0})
        self.assertIn("Last one standing", [h["title"] for h in g.highlights()])

    def test_survival_out_players_cannot_answer_and_dont_hold_up_the_round(self):
        g, clock = make(3, style="survival")
        g.lives["p2"] = 0
        g.handle("p0", {"a": "answer", "choice": 0})
        with self.assertRaises(GameError):
            g.handle("p2", {"a": "answer", "choice": 0})
        g.handle("p1", {"a": "answer", "choice": 0})
        self.assertEqual(g.phase, "reveal")

    def test_solo_survival_runs_until_the_lives_are_gone(self):
        g, clock = make(1, style="survival")
        for _ in range(4):
            g.handle("p0", {"a": "answer", "choice": right(g)})
            g.advance()
        for _ in range(LIVES):
            g.handle("p0", {"a": "answer", "choice": wrong(g)})
            g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(g.round_scores["p0"], 400)

    def test_wager(self):
        g, clock = make(3, style="wager")
        self.assertEqual(g.phase, "wager")
        v = g.view_for("p0")
        self.assertIsNone(v["question"])  # the category and level only
        self.assertTrue(v["category"]["label"] and v["level"])
        self.assertEqual(v["you"]["max_wager"], 300)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "wager", "amount": 301})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "answer", "choice": 0})
        g.handle("p0", {"a": "wager", "amount": 300})
        g.handle("p1", {"a": "wager", "amount": 200})
        self.assertEqual(g.view_for("p2")["wagered"], ["p0", "p1"])
        self.assertNotIn("300", json.dumps(g.view_for("p2")["wagered"]))
        clock.t += 12
        g.tick()  # p2 never bet: 0
        self.assertEqual(g.phase, "question")
        g.handle("p0", {"a": "answer", "choice": right(g)})
        g.handle("p1", {"a": "answer", "choice": wrong(g)})
        g.handle("p2", {"a": "answer", "choice": right(g)})
        self.assertEqual(g.result["gains"], {"p0": 400, "p1": -200, "p2": 100})
        g.advance()
        self.assertEqual(g.view_for("p0")["you"]["max_wager"], 400)

    def test_draft_rotates_the_pick(self):
        g, clock = make(3, style="draft")
        self.assertEqual((g.phase, g.picker), ("pick", "p0"))
        offers = [o["id"] for o in g.view_for("p1")["pick"]["offers"]]
        self.assertEqual(len(set(offers)), 3)
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "pick", "cat": offers[0]})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "pick", "cat": "gossip"})
        g.handle("p0", {"a": "pick", "cat": offers[1]})
        self.assertEqual((g.phase, g.cat), ("question", offers[1]))
        clock.t += 30
        g.tick()
        g.advance()
        self.assertEqual(g.picker, "p1")
        self.assertNotIn(offers[1], [o["id"] for o in g.view_for("p1")["pick"]["offers"]])
        clock.t += 12
        g.tick()  # nobody picked in time: one is chosen
        self.assertEqual(g.phase, "question")

    def test_draft_with_one_topic_plays_classic(self):
        g, _ = make(2, style="draft", topic="music")
        self.assertEqual((g.style, g.phase), ("classic", "question"))

    def test_theme_pack_leans_on_its_category(self):
        clock = Clock()
        g = TriviaTonight(
            [Player("p0", "A")],
            rng=random.Random(3),
            clock=clock,
            theme="movies",
            options={"questions": "20"},
        )
        g.start()
        cats = []
        while not g.finished:
            if g.phase == "question":
                cats.append(g.cat)
            clock.t += 30
            g.tick()
        self.assertGreater(cats.count("screen"), 6)


class SecrecyTests(unittest.TestCase):
    def test_every_phase_every_screen(self):
        for style in ("classic", "fastest", "survival", "wager", "draft"):
            g, clock = make(3, style=style, questions="5")
            guard = 0
            while not g.finished and guard < 200:
                guard += 1
                for pid in [*g.player_ids, *SPECTATORS]:
                    v = g.view_for(pid)
                    json.dumps(v)
                    if g.phase in ("pick", "wager", "question"):
                        self.assertNotIn("result", v)
                        self.assertNotIn("history", v)
                        self.assertTrue(secret_free(g, pid), (style, g.phase))
                if g.phase == "question":
                    g.handle("p0", {"a": "answer", "choice": right(g)})
                    for pid in ["p1", *SPECTATORS]:
                        v = g.view_for(pid)
                        self.assertEqual(v["answered"], ["p0"])  # who, never what
                        self.assertNotIn("picks", json.dumps(v))
                        if pid != "p0" and v["you"] is not None:
                            self.assertIsNone(v["you"]["answer"])
                    self.assertEqual(g.view_for("p0")["you"]["answer"], right(g))
                if g.phase == "pick":
                    g.handle(g.picker, {"a": "pick", "cat": g.offers[0]})
                    continue
                clock.t += 31
                g.tick()
            self.assertTrue(g.finished, style)
            for pid in [*g.player_ids, *SPECTATORS]:
                v = g.view_for(pid)
                json.dumps(v)
                self.assertIn("history", v)
            self.assertIsNone(g.view_for("tv:screen")["you"])
            self.assertIsNone(g.view_for("au:fan")["you"])

    def test_spectators_cannot_act(self):
        g, _ = make(2)
        for pid in SPECTATORS:
            with self.assertRaises(GameError):
                g.handle(pid, {"a": "answer", "choice": 0})

    def test_reveal_shows_answer_picks_and_times(self):
        g, clock = make(2)
        clock.t += 2.5
        g.handle("p0", {"a": "answer", "choice": right(g)})
        g.handle("p1", {"a": "answer", "choice": wrong(g)})
        v = g.view_for("tv:screen")
        self.assertEqual(v["result"]["right"], right(g))
        self.assertEqual(v["result"]["answer"], TRIVIA[g.qi]["a"])
        self.assertEqual(v["result"]["picks"], {"p0": right(g), "p1": wrong(g)})
        self.assertEqual(v["result"]["times"]["p0"], 2500)

    def test_chat_is_muted_only_while_a_question_is_up(self):
        g, clock = make(2)
        self.assertTrue(g.chat_muted("p0"))
        clock.t += 30
        g.tick()
        self.assertFalse(g.chat_muted("p0"))

    def test_peek_is_a_fifty_fifty_that_never_names_the_answer(self):
        for seed in range(20):
            g, _ = make(2, seed=seed)
            line = g.peek("p0")
            if len(g.choices) == 2:
                self.assertIsNone(line)
                continue
            self.assertNotIn(f"“{TRIVIA[g.qi]['a']}”", line)
            self.assertEqual(sum(f"“{c}”" in line for c in g.choices), 2)


if __name__ == "__main__":
    unittest.main()
