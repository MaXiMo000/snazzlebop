"""Public pages carry real content in the first HTML (for crawlers): every game is linked, each game's
page has its rules, catalogue text is escaped, rooms and private pages are left alone."""

from __future__ import annotations

import unittest

from app import pages
from app.games import catalog, catalogue

INDEX = (
    '<!doctype html><html><head><meta name="description" content="old" />'
    '<title>old</title></head><body><div id="root"></div></body></html>'
)


class PageTests(unittest.TestCase):
    def setUp(self):
        self.games = catalog()
        self.cats = catalogue.categories()

    def test_home_links_every_game(self):
        title, desc, body = pages.page_for("", self.games, self.cats)
        self.assertIn("Snazzlebop", title)
        self.assertTrue(desc)
        for g in self.games:
            self.assertIn(f'href="/games/{g["id"]}"', body)

    def test_each_game_page_has_its_rules(self):
        for g in self.games:
            page = pages.page_for(f"games/{g['id']}", self.games, self.cats)
            self.assertIsNotNone(page, g["id"])
            title, _desc, body = page
            self.assertIn("How to play", body)
            self.assertGreater(body.count("<li>"), 0, g["id"])
            self.assertTrue(title.startswith(g["title"].replace("&", "&amp;")) or g["title"] in title)

    def test_rooms_unknown_games_and_private_pages_are_left_alone(self):
        for path in ("r/ABCDE", "games/nope", "account", "clubs", "inbox", "games/../etc"):
            self.assertIsNone(pages.page_for(path, self.games, self.cats), path)

    def test_catalogue_text_is_escaped(self):
        evil = [{**self.games[0], "id": "x1", "title": "<script>alert(1)</script>", "blurb": '"><img src=x>'}]
        cats = [{**self.cats[0], "id": evil[0]["category"]}]
        title, desc, body = pages.page_for("games/x1", evil, cats)
        out = pages.render(INDEX, (title, desc, body))
        self.assertNotIn("<script>alert", out)
        self.assertNotIn('"><img', out)

    def test_render_and_sitemap(self):
        out = pages.render(INDEX, ("New & shiny", 'Say "hi"', "<p>body</p>"))
        self.assertIn("<title>New &amp; shiny</title>", out)
        self.assertIn('content="Say &quot;hi&quot;"', out)
        self.assertIn('<div id="root"><p>body</p></div>', out)
        xml = pages.sitemap("https://snazzlebop.com/", self.games)
        self.assertIn("<loc>https://snazzlebop.com/games/trivia</loc>", xml)
        self.assertEqual(xml.count("<url>"), 7 + len(self.games))


if __name__ == "__main__":
    unittest.main()


def test_the_server_sends_each_public_page_with_its_content(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_api import settings

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(INDEX, encoding="utf-8")
    with TestClient(create_app(settings(tmp_path, static_dir=str(static)))) as c:
        r = c.get("/games/trivia")
        assert r.status_code == 200 and "<title>Trivia Tonight: how to play" in r.text
        assert "How to play" in r.text and "<li>" in r.text
        assert '<link rel="canonical" href="' in r.text and '/games/trivia" />' in r.text
        home = c.get("/").text
        assert 'href="/games/chess"' in home and "<title>Snazzlebop: party game show" in home
        assert c.get("/about").status_code == 200
        room = c.get("/r/ABCDE").text
        assert room == INDEX  # rooms: just the app, nothing for a crawler
        assert c.get("/games/nope").text == INDEX
        assert c.head("/sitemap.xml").status_code == 200  # crawlers check before reading
        assert c.head("/ads.txt").status_code == 200
        assert c.head("/games/trivia").status_code == 200
        xml = c.get("/sitemap.xml")
        assert xml.headers["content-type"].startswith("application/xml") and "/games/trivia</loc>" in xml.text
