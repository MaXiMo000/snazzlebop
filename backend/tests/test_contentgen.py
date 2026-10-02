"""Generated content: strict validation, de-duplication, background generation, fallback, persistence."""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace

from app.contentgen import KINDS, ContentGenerator, add_items, claude_caller, v_alibi, v_crossword, v_price


class PoolSnapshot(unittest.IsolatedAsyncioTestCase):
    """Pools are shared module state: put them back after every test."""

    def setUp(self):
        self._saved = {k: list(spec.pool) for k, spec in KINDS.items()}

    def tearDown(self):
        for k, spec in KINDS.items():
            spec.pool[:] = self._saved[k]


class ValidationTests(unittest.TestCase):
    def test_price_items(self):
        ok = v_price({"name": "Moon boots", "blurb": "Bouncy beyond belief.", "emoji": "🥾", "price": 301})
        self.assertEqual(ok["price"], 302)  # always even, so a x1/2 spin stays whole
        for bad in (
            {"name": "Moon boots", "blurb": "Visit www.shop.com now", "emoji": "🥾", "price": 30},
            {"name": "<b>Boots</b>", "blurb": "Bouncy beyond belief.", "emoji": "🥾", "price": 30},
            {"name": "Moon boots", "blurb": "Bouncy beyond belief.", "emoji": "AB", "price": 30},
            {"name": "Moon boots", "blurb": "Bouncy beyond belief.", "emoji": "🥾", "price": True},
            {"name": "Moon boots", "blurb": "Bouncy beyond belief.", "emoji": "🥾", "price": 99_999_999},
            {"name": "Cheap beer", "blurb": "For the grown-ups.", "emoji": "🍺", "price": 4},
            {"name": "Moon‮boots", "blurb": "Bouncy beyond belief.", "emoji": "🥾", "price": 30},
            "not a dict",
        ):
            self.assertIsNone(v_price(bad), bad)

    def test_alibi_needs_six_distinct_locations_and_slots(self):
        good = {
            "title": "Trouble at the Treehouse",
            "victim": "Sir Acorn",
            "locations": ["Ladder", "Lookout", "Rope bridge", "Hammock", "Snack shelf", "Trapdoor"],
            "slots": ["4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM", "6:00 PM", "6:30 PM"],
        }
        self.assertIsNotNone(v_alibi(good))
        self.assertIsNone(v_alibi({**good, "locations": good["locations"][:5]}))
        self.assertIsNone(v_alibi({**good, "locations": [*good["locations"][:5], "ladder"]}))

    def test_crossword_never_gives_the_answer_away(self):
        self.assertEqual(v_crossword({"word": "otter", "clue": "Playful river swimmer"})["word"], "OTTER")
        for bad in (
            {"word": "OTTER", "clue": "An otter, obviously"},
            {"word": "OT TER", "clue": "Playful river swimmer"},
            {"word": "HIPPOPOTAMUS", "clue": "Too long for our grids"},
            {"word": "NO", "clue": "Too short"},
        ):
            self.assertIsNone(v_crossword(bad), bad)


class AddItemsTests(PoolSnapshot):
    async def test_prompt_lists_every_taken_short_key(self):
        gen = ContentGenerator(None)
        prompt = gen.prompt("crossword")
        self.assertTrue(all(e["word"] in prompt for e in KINDS["crossword"].pool))

    async def test_dedupes_against_pool_and_batch(self):
        pool = KINDS["frenemy"].pool
        before = len(pool)
        existing = pool[0]
        added = add_items(
            "frenemy",
            [
                existing,  # already in the pool
                existing.upper() + "!",  # same normalised key (case and punctuation ignored)
                "Most likely to name a houseplant after a wizard",
                "most likely to NAME a houseplant after a wizard",  # same key within the batch
                "Most likely to visit www.example.com",  # URL
                "",
            ],
        )
        self.assertEqual(added, ["Most likely to name a houseplant after a wizard"])
        self.assertEqual(len(pool), before + 1)


class GeneratorTests(PoolSnapshot):
    async def test_generates_in_background_validates_and_persists(self):
        saved = []

        async def call(system, schema, prompt):
            self.assertIn("already used", prompt.lower())
            self.assertEqual(schema["required"], ["items"])
            return {
                "items": [
                    {"word": "QUOKKA", "clue": "Smiley wallaby relative"},
                    {"word": "QUOKKA", "clue": "Duplicate in the same batch"},
                    {"word": "X1", "clue": "Rejected"},
                ]
            }

        async def save(kind, items):
            saved.append((kind, items))

        gen = ContentGenerator(call, save=save)
        gen.request("crossword")
        await asyncio.gather(*gen.tasks)
        self.assertIn({"word": "QUOKKA", "clue": "Smiley wallaby relative"}, KINDS["crossword"].pool)
        self.assertEqual(
            saved, [("crossword", [("QUOKKA", {"word": "QUOKKA", "clue": "Smiley wallaby relative"})])]
        )
        self.assertEqual(gen.stats["added"], 1)

    async def test_off_without_a_key(self):
        gen = ContentGenerator(None)
        gen.request("frenemy")
        self.assertFalse(gen.tasks)
        self.assertFalse(gen.enabled)

    async def test_failure_backs_off_and_pools_carry_on(self):
        clock = [0.0]
        calls = []

        async def call(system, schema, prompt):
            calls.append(1)
            raise RuntimeError("429 rate limited")

        gen = ContentGenerator(call, clock=lambda: clock[0])
        before = len(KINDS["price"].pool)
        gen.request("price")
        await asyncio.gather(*gen.tasks)
        self.assertEqual(len(KINDS["price"].pool), before)
        gen.request("price")  # cooling down: no second call
        await asyncio.gather(*gen.tasks)
        self.assertEqual(len(calls), 1)
        clock[0] += 301
        gen.request("price")
        await asyncio.gather(*gen.tasks)
        self.assertEqual(len(calls), 2)
        clock[0] += 301  # second failure doubled the cooldown to 600 s
        gen.request("price")
        await asyncio.gather(*gen.tasks)
        self.assertEqual(len(calls), 2)

    async def test_hourly_budget_and_one_call_per_kind_at_a_time(self):
        clock = [0.0]
        release = asyncio.Event()

        async def call(system, schema, prompt):
            await release.wait()
            return {"items": []}

        gen = ContentGenerator(call, calls_per_hour=2, clock=lambda: clock[0])
        gen.request("mural")
        gen.request("mural")  # busy with this kind already
        self.assertEqual(len(gen.tasks), 1)
        gen.request("telepathy")
        gen.request("alibi")  # budget of 2 per hour spent
        self.assertEqual(len(gen.tasks), 2)
        release.set()
        await asyncio.gather(*gen.tasks)
        clock[0] += 3601
        gen.request("alibi")
        self.assertEqual(len(gen.tasks), 1)
        await asyncio.gather(*gen.tasks)


class ClaudeCallerTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_shape_and_refusal_handling(self):
        sent = {}

        async def create(**kw):
            sent.update(kw)
            return SimpleNamespace(
                stop_reason=sent.get("_stop", "end_turn"),
                content=[SimpleNamespace(type="text", text=json.dumps({"items": []}))],
            )

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        call = claude_caller("unused", "claude-opus-5-5", client=client)
        self.assertEqual(await call("sys", {"type": "object"}, "go"), {"items": []})
        self.assertEqual(sent["model"], "claude-opus-5-5")
        self.assertEqual(sent["fallbacks"], "default")
        self.assertEqual(sent["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(sent["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(sent["output_config"]["effort"], "low")

        async def refuse(**kw):
            return SimpleNamespace(stop_reason="refusal", content=[])

        client.beta.messages.create = refuse
        with self.assertRaises(ValueError):
            await claude_caller("unused", client=client)("sys", {}, "go")


class PersistenceTests(PoolSnapshot):
    async def test_saved_content_survives_a_restart(self):
        from app.db import Database

        db = Database("sqlite+aiosqlite:///:memory:")
        await db.init()
        item = {"word": "QUOKKA", "clue": "Smiley Australian marsupial"}
        await db.save_content("crossword", [("QUOKKA", item)])
        await db.save_content("crossword", [("QUOKKA", item)])  # duplicate: skipped, no error
        rows = await db.load_content()
        self.assertEqual(rows, [("crossword", item)])
        self.assertEqual(add_items("crossword", [rows[0][1]]), [item])
        await db.close()


class ExtraFileTests(PoolSnapshot):
    async def test_committed_extras_go_through_the_same_validator(self):
        import tempfile
        from pathlib import Path

        from app.contentgen import load_extra

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "extra.json"
            f.write_text(
                json.dumps(
                    {
                        "crossword": [
                            {"word": "NARWHAL", "clue": "Unicorn of the sea"},
                            {"word": "NARWHAL", "clue": "Duplicate"},
                            {"word": "BAD WORD", "clue": "Rejected"},
                        ],
                        "not_a_kind": [1, 2],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_extra(f), 1)
            f.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_extra(f), 0)  # unreadable: built-in pools carry on


if __name__ == "__main__":
    unittest.main()
