"""Draw Telephone: passing the books round, timeouts, the album, likes, secrecy, and the hub's ink rules."""

from __future__ import annotations

import asyncio
import json
import random
import unittest

from app.games import GameError, Player
from app.games.content import TELEPHONE_IDEAS
from app.games.telephone import LIKE_POINTS, TIMEOUT_TEXT, DrawTelephone

from .test_rooms import FakeConn, HubHarness

SPECTATORS = ("tv:screen", "au:fan")
STROKE = {"op": "line", "c": 0, "w": 1, "p": [10, 10, 50, 50]}


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1, **opts):
    clock = Clock()
    g = DrawTelephone(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def play_steps(g):
    """Everyone writes / draws / describes; returns what each player wrote at step 0."""
    first = {}
    while g.phase in ("write", "draw", "describe"):
        for pid in g.order:
            if g.phase == "write":
                first[pid] = f"sentence by {pid}"
                g.handle(pid, {"a": "text", "text": first[pid]})
            elif g.phase == "draw":
                g.ink(pid, STROKE)
                g.handle(pid, {"a": "done"})
            else:
                g.handle(pid, {"a": "text", "text": f"guess by {pid} at {g.step}"})
    return first


class FlowTests(unittest.TestCase):
    def test_books_travel_the_circle(self):
        g, _ = make(4)
        self.assertEqual(g.phase, "write")
        self.assertIn(g.view_for("p0")["task"]["idea"], TELEPHONE_IDEAS)
        first = play_steps(g)
        self.assertEqual(g.phase, "album")
        for b, book in enumerate(g.books):
            self.assertEqual([pg["kind"] for pg in book], ["text", "drawing", "text", "drawing"])
            # Book b starts with its owner, then visits each next player once.
            self.assertEqual([pg["by"] for pg in book], [g.order[(b + s) % 4] for s in range(4)])
            self.assertEqual(book[0]["text"], first[g.order[b]])

    def test_draw_works_from_the_previous_page_and_describe_from_the_drawing(self):
        g, _ = make(3)
        for pid in g.order:
            g.handle(pid, {"a": "text", "text": f"hello from {pid}"})
        self.assertEqual(g.phase, "draw")
        for pid in g.order:
            task = g.view_for(pid)["task"]
            book = g.books[g._book_of(pid)]
            self.assertEqual(task["prompt"], book[0]["text"])
            self.assertNotIn("from", task)  # anonymous until the album names everyone
        for pid in g.order:
            g.handle(pid, {"a": "done"})
        self.assertEqual(g.phase, "describe")
        for pid in g.order:
            task = g.view_for(pid)["task"]
            self.assertEqual(task["drawing"], g.books[g._book_of(pid)][1]["canvas"].id)
            self.assertIs(g.drawing(pid, task["drawing"]), g.books[g._book_of(pid)][1]["canvas"])

    def test_timeouts_fill_in(self):
        g, clock = make(3)
        g.handle(g.order[0], {"a": "text", "text": "mine"})
        clock.t += 45
        g.tick()
        self.assertEqual(g.phase, "draw")
        texts = {g.books[b][0]["by"]: g.books[b][0]["text"] for b in range(3)}
        self.assertEqual(texts[g.order[0]], "mine")
        self.assertEqual(texts[g.order[1]], g.ideas[g.order[1]])  # the suggested idea
        clock.t += g.draw_seconds
        g.tick()
        self.assertEqual(g.phase, "describe")
        clock.t += 40
        g.tick()
        self.assertEqual(g.phase, "album")
        self.assertTrue(all(g.books[b][2]["text"] == TIMEOUT_TEXT for b in range(3)))

    def test_text_validation_and_resubmit(self):
        g, _ = make(3)
        pid = g.order[0]
        for bad in (None, 3, "", "  ", "x" * 81, "a\nb", "‮evil"):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle(pid, {"a": "text", "text": bad})
        g.handle(pid, {"a": "text", "text": "first  try"})
        g.handle(pid, {"a": "text", "text": "second try"})
        self.assertEqual(g.pending[pid], "second try")
        with self.assertRaises(GameError):
            g.handle(pid, {"a": "done"})  # not a drawing step
        with self.assertRaises(GameError):
            g.handle(pid, {"a": "fly"})

    def test_drawing_rules(self):
        g, _ = make(3)
        with self.assertRaises(GameError):
            g.ink(g.order[0], STROKE)  # writing, not drawing
        for pid in g.order:
            g.handle(pid, {"a": "text", "text": "x"})
        canvases = {pid: g.ink(pid, STROKE) for pid in g.order}
        self.assertEqual(len({c.id for c in canvases.values()}), 3)  # one canvas each
        for pid in g.order:
            self.assertIs(g.canvas_for(pid), canvases[pid])
        for spectator in SPECTATORS:
            self.assertIsNone(g.canvas_for(spectator))
        g.handle(g.order[0], {"a": "done"})
        g.handle(g.order[0], {"a": "done", "done": False})  # changed their mind
        self.assertNotIn(g.order[0], g.done)
        with self.assertRaises(GameError):
            g.handle(g.order[0], {"a": "done", "done": "yes"})

    def test_album_pages_likes_and_final(self):
        g, clock = make(3)
        play_steps(g)
        self.assertEqual((g.book, g.entry), (0, 0))
        view = g.view_for("tv:screen")
        self.assertEqual(len(view["album"]["pages"]), 1)
        author = g.books[0][0]["by"]
        fan = next(p for p in g.order if p != author)
        with self.assertRaises(GameError):
            g.handle(author, {"a": "like", "book": 0, "entry": 0})  # your own page
        with self.assertRaises(GameError):
            g.handle(fan, {"a": "like", "book": 0, "entry": 1})  # not out yet
        for bad in ((True, 0), (0, None), (-1, 0), (9, 0)):
            with self.assertRaises(GameError):
                g.handle(fan, {"a": "like", "book": bad[0], "entry": bad[1]})
        g.handle(fan, {"a": "like", "book": 0, "entry": 0})
        self.assertEqual(g.scores()[author], LIKE_POINTS)
        self.assertTrue(g.view_for(fan)["album"]["pages"][0]["liked"])
        g.handle(fan, {"a": "like", "book": 0, "entry": 0})  # unlike
        self.assertEqual(g.scores()[author], 0)
        g.handle(fan, {"a": "like", "book": 0, "entry": 0})
        stages = {g.stage}
        while not g.finished:
            clock.t += 10
            g.tick()
            stages.add(g.stage)
        self.assertEqual(len(stages), 3 * 3 + 1)  # every page, then the final screen
        final = g.view_for("p0")
        self.assertEqual(len(final["books"]), 3)
        last = g.books[2][2]
        liker = next(p for p in g.order if p != last["by"])
        g.handle(liker, {"a": "like", "book": 2, "entry": 2})  # likes still count on the final screen
        self.assertEqual(g.view_for(liker)["books"][2]["pages"][2]["likes"], 1)
        self.assertTrue(g.highlights())
        json.dumps(final)


class SecrecyTests(unittest.TestCase):
    def test_nobody_sees_another_book_before_the_album(self):
        g, _ = make(4)
        secrets_ = []
        while g.phase in ("write", "draw", "describe"):
            for pid in g.order:
                if g.phase == "draw":
                    g.ink(pid, STROKE)
                    g.handle(pid, {"a": "done"})
                else:
                    text = f"secret-{pid}-{g.step}"
                    secrets_.append((pid, g.step, text))
                    g.handle(pid, {"a": "text", "text": text})
                if g.phase not in ("write", "draw", "describe"):
                    break
                for viewer in [*g.order, *SPECTATORS]:
                    blob = json.dumps(g.view_for(viewer))
                    task = g.view_for(viewer)["task"]
                    allowed = {task["prompt"]} if task and task.get("prompt") else set()
                    if task and task.get("text"):
                        allowed.add(task["text"])
                    for _, _, text in secrets_:
                        if text not in allowed:
                            self.assertNotIn(text, blob, viewer)
                    # Only the drawing you describe, never anyone else's.
                    for book in g.books:
                        for pg in book:
                            if pg["kind"] == "drawing":
                                mine = task and task.get("drawing") == pg["canvas"].id
                                seen = g.drawing(viewer, pg["canvas"].id) is not None
                                self.assertEqual(seen, bool(mine), viewer)
        self.assertEqual(g.phase, "album")
        # The album shows pages only as they're revealed.
        hidden = g.books[0][1]["canvas"].id
        self.assertIsNone(g.drawing("tv:screen", hidden))
        g.advance()
        self.assertIs(g.drawing("tv:screen", hidden), g.books[0][1]["canvas"])
        later = g.books[1][0]["text"]
        self.assertNotIn(later, json.dumps(g.view_for("au:fan")))


class HubInkTests(HubHarness):
    async def test_telephone_drawings_are_never_relayed_and_sync_only_what_you_may_see(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        _, _tv = hub.issue_tv(room.code)
        vid = next(iter(room.viewers))
        screen = FakeConn()
        await hub.connect(room, vid, screen)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "telephone"})
        g = room.game
        for pid in g.order:
            await hub.handle_message(room, pid, conns[pid], {"t": "act", "a": "text", "text": f"hi {pid}"})
        self.assertEqual(g.phase, "draw")
        artist = g.order[0]
        await hub.handle_message(room, artist, conns[artist], {"t": "ink", **STROKE})
        await asyncio.sleep(0.05)
        for to, c in [*conns.items(), (vid, screen)]:
            self.assertEqual([m for m in c.sent if m["t"] == "ink"], [], to)
        # The artist's own screen can get its drawing back (a reload)...
        await hub.handle_message(room, artist, conns[artist], {"t": "inksync"})
        canvas_id = g.canvas_for(artist).id
        # ...but nobody else can ask for it by id.
        await hub.handle_message(room, vid, screen, {"t": "inksync", "id": canvas_id})
        other = g.order[1]
        await hub.handle_message(room, other, conns[other], {"t": "inksync", "id": canvas_id})
        await hub.handle_message(room, other, conns[other], {"t": "inksync", "id": ["x"]})
        await asyncio.sleep(0.05)
        got = [m for m in conns[artist].sent if m["t"] == "ink"]
        self.assertEqual((got[-1]["id"], got[-1]["full"], len(got[-1]["ops"])), (canvas_id, True, 1))
        self.assertEqual([m for m in screen.sent if m["t"] == "ink"], [])
        self.assertEqual([m for m in conns[other].sent if m["t"] == "ink"], [])


if __name__ == "__main__":
    unittest.main()


class AnonymousTests(unittest.TestCase):
    def test_nobody_is_named_until_the_book_is_finished(self):
        g, _ = make(3)
        play_steps(g)
        tv = "tv:screen"
        for viewer in [*g.order, tv]:
            album = g.view_for(viewer)["album"]
            self.assertIsNone(album["owner"])
            self.assertFalse(album["named"])
            self.assertEqual([pg["by"] for pg in album["pages"]], [None])
            self.assertEqual(album["pages"][0]["mine"], viewer == g.books[0][0]["by"])
        while g.entry < len(g.order) - 1:
            self.assertTrue(all(pg["by"] is None for pg in g.view_for(tv)["album"]["pages"]))
            g.advance()
        album = g.view_for(tv)["album"]
        self.assertEqual(album["owner"], g.order[0])
        self.assertEqual([pg["by"] for pg in album["pages"]], [pg["by"] for pg in g.books[0]])
        g.advance()  # the next book starts anonymous again
        self.assertIsNone(g.view_for(tv)["album"]["owner"])
