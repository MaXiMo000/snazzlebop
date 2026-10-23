"""The catalogue: every game has a valid category, the featured row and ranked set name real games, and
the lobby gets the categories in shelf order."""

from __future__ import annotations

import unittest

from app.games import REGISTRY, catalog
from app.games.catalogue import CATEGORIES, CATEGORY_OF, FEATURED, RANKED, categories


class CatalogueTests(unittest.TestCase):
    def test_every_game_has_exactly_one_known_category(self):
        ids = {cid for cid, _, _, _ in CATEGORIES}
        self.assertEqual(set(CATEGORY_OF), set(REGISTRY))
        self.assertTrue(set(CATEGORY_OF.values()) <= ids)
        self.assertEqual(len(ids), len(CATEGORIES))
        for cid in ids:  # no empty shelf
            self.assertIn(cid, CATEGORY_OF.values())

    def test_featured_and_ranked_name_real_games(self):
        self.assertEqual(len(set(FEATURED)), len(FEATURED))
        self.assertTrue(set(FEATURED) <= set(REGISTRY))
        self.assertTrue(RANKED.issubset(REGISTRY))

    def test_cards_carry_the_catalogue_fields(self):
        cards = {c["id"]: c for c in catalog()}
        self.assertEqual(cards["imposter"]["featured"], 0)
        self.assertIsNone(cards["ludo"]["featured"])
        self.assertTrue(cards["chess"]["ranked"])
        self.assertFalse(cards["roulette"]["ranked"])  # luck games never rate anyone
        self.assertEqual(cards["trivia"]["category"], "quiz")
        self.assertEqual([c["id"] for c in categories()], [cid for cid, _, _, _ in CATEGORIES])


class OptionLabelTests(unittest.TestCase):
    def test_every_option_value_has_a_label_in_the_lobby(self):
        """Contract with frontend/src/lib/options.ts: an unlabelled option shows its raw value ("3")."""
        import re
        from pathlib import Path

        ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "options.ts").read_text(
            "utf-8"
        )
        blocks = {
            m.group(1): m.group(2)
            for m in re.finditer(r"^\s{2}([a-z]+): \{(.*?)\n?\s*\},?$", ts, re.M | re.S)
        }
        for game_id, cls in REGISTRY.items():
            for key, values in cls.OPTIONS.items():
                self.assertIn(key, blocks, f"{game_id}: no labels for option {key!r}")
                for value in values:
                    self.assertRegex(
                        blocks[key], rf'(^|[\s{{,])"?{re.escape(value)}"?:', f"{game_id}.{key}={value}"
                    )
