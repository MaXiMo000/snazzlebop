"""Show packs (themed dealing) and the host's one-liner templates."""

from __future__ import annotations

import copy
import random
import unittest

from app.contentgen import KINDS, add_items, load_extra, v_quip
from app.games import Player
from app.games import content as C
from app.games.base import Deck
from app.games.frenemy import FrenemyRadar


class Snapshot(unittest.TestCase):
    def setUp(self):
        self._pools = {k: list(spec.pool) for k, spec in KINDS.items()}
        self._themed = copy.deepcopy(C.THEMED)

    def tearDown(self):
        for k, spec in KINDS.items():
            spec.pool[:] = self._pools[k]
        C.THEMED.clear()
        C.THEMED.update(self._themed)


class DeckPreferTests(unittest.TestCase):
    def test_preferred_cards_first_then_the_rest_and_never_a_repeat(self):
        deck = Deck(30, random.Random(1))
        prefer = {3, 7, 11, 19}
        first = deck.draw(3, prefer)
        self.assertTrue(set(first) <= prefer)
        second = deck.draw(5, prefer)
        self.assertIn(set(prefer) - set(first), [set(second) & prefer])  # the last preferred card leads
        rest = deck.draw(22)
        dealt = first + second + rest
        self.assertEqual(sorted(dealt), list(range(30)))  # one full pass: every card exactly once

    def test_preferred_cards_come_back_first_on_the_next_pass(self):
        deck = Deck(10, random.Random(2))
        deck.draw(10)
        self.assertEqual(set(deck.draw(2, {4, 5})), {4, 5})


class ThemeTaggingTests(Snapshot):
    def test_tags_new_and_existing_items_and_games_deal_them_first(self):
        existing = KINDS["frenemy"].pool[0]
        added = add_items(
            "frenemy", [existing, "Most likely to direct a blockbuster about their cat"], "movies"
        )
        self.assertEqual(len(added), 1)  # the existing prompt isn't added twice...
        tagged = C.THEMED["frenemy"]["movies"]
        self.assertEqual(len(tagged), 2)  # ...but it is tagged
        game = FrenemyRadar(
            [Player(id=f"p{i}", name=f"N{i}") for i in range(3)], rng=random.Random(5), theme="movies"
        )
        game.start()
        prompts = set(game.prompts)
        self.assertEqual(
            prompts & {KINDS["frenemy"].pool[i] for i in tagged}, {KINDS["frenemy"].pool[i] for i in tagged}
        )

    def test_unknown_theme_is_refused(self):
        with self.assertRaises(ValueError):
            add_items("frenemy", ["Most likely to bake a perfect loaf"], "nope")

    def test_extra_file_theme_packs_load_after_plain_pools(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extra.json"
            path.write_text(
                json.dumps(
                    {
                        "frenemy#spooky": ["Most likely to teach a shy ghost to juggle teacups"],
                        "frenemy": ["Most likely to teach a shy ghost to juggle teacups"],
                        "bogus#spooky": ["x"],
                        "frenemy#bogus": ["x"],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_extra(path), 1)
        idx = KINDS["frenemy"].pool.index("Most likely to teach a shy ghost to juggle teacups")
        self.assertEqual(C.THEMED["frenemy"]["spooky"], {idx})


class QuipTests(unittest.TestCase):
    def test_every_seed_quip_is_valid(self):
        for q in C.QUIPS:
            self.assertEqual(v_quip(q), q, q["text"])
        for mood in C.QUIP_MOODS:
            self.assertGreaterEqual(sum(q["mood"] == mood for q in C.QUIPS), 8, mood)

    def test_validator_rejects_unknown_placeholders_and_markup(self):
        ok = {"mood": "win", "text": "{winner} takes {game}, what a night for everyone!"}
        self.assertEqual(v_quip(ok), ok)
        for text in (
            "{winner} won {game} and {0.__class__} is here",  # format-string tricks never get in
            "{winner} won thanks to {secret_field}, wow amazing",
            "Somebody won {game}! What a wonderful night it was",  # no {winner}
            "{winner} won {game}, see www.example.com for more!",
            "{winner} won <b>{game}</b>, what a night for everyone",
        ):
            self.assertIsNone(v_quip({"mood": "win", "text": text}), text)
        self.assertIsNone(v_quip({"mood": "close", "text": "{winner} won by a whisker, unbelievable!"}))
        self.assertIsNone(v_quip({"mood": "smug", "text": "{winner} takes {game}, what a night!"}))


if __name__ == "__main__":
    unittest.main()
