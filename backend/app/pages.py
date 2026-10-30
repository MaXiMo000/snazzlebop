"""Server-written HTML for the public pages: a real title, description and readable text in the very
first response, so search and ad crawlers see the site's content even before (or without) its
JavaScript. The app replaces it when it starts. Pure: the game catalogue is passed in; everything that
comes from it is escaped.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from html import escape
from typing import Any

SITE = "Snazzlebop"
TAGLINE = "The party game show where your friends are the contestants."
SUMMARY = (
    "Snazzlebop is a free party game show for 1 to 8 friends plus an audience: trivia, bluffing, "
    "drawing, quick-fire show games and the classics. One person hosts on a laptop or TV, everyone "
    "else joins from their phone with a five-letter code. No sign-up, no download."
)
STEPS = (
    "Host a room: type your name and get a five-letter code.",
    "Friends join on their phones with the code or the invite link. Put the show on a TV if you like.",
    "Pick a game. Each one teaches its rules in a few seconds, then the show keeps score.",
)
GAME_PATH = re.compile(r"games/([a-z0-9]{2,24})/?")

Page = tuple[str, str, str]  # title, description, body HTML


def _link(href: str, text: str) -> str:
    return f'<a href="{escape(href)}">{escape(text)}</a>'


def _players(g: dict[str, Any]) -> str:
    lo, hi = g["min_players"], g["max_players"]
    return f"{lo} player{'s' if lo != 1 else ''}" if lo == hi else f"{lo}-{hi} players"


def _game_list(games: Sequence[dict[str, Any]], categories: Sequence[dict[str, str]]) -> str:
    parts = []
    for cat in categories:
        rows = [g for g in games if g.get("category") == cat["id"]]
        if not rows:
            continue
        items = "".join(
            f"<li>{_link('/games/' + g['id'], g['title'])}: {escape(g['blurb'])} ({_players(g)})</li>"
            for g in rows
        )
        parts.append(f"<h3>{escape(cat['title'])}</h3><p>{escape(cat['blurb'])}</p><ul>{items}</ul>")
    return "".join(parts)


def _shell(body: str) -> str:
    links = " · ".join(
        _link(href, text)
        for href, text in (
            ("/", "Play"),
            ("/games", "All games"),
            ("/about", "About"),
            ("/plus", "Plus"),
            ("/terms", "Terms"),
            ("/privacy", "Privacy"),
        )
    )
    return f'<div class="prerender prose-page"><nav aria-label="Site">{links}</nav>{body}</div>'


def page_for(path: str, games: Sequence[dict[str, Any]], categories: Sequence[dict[str, str]]) -> Page | None:
    """The title, description and body for a public page, or None to leave the page as it is
    (rooms and signed-in pages: nothing for a crawler there)."""
    path = path.strip("/")
    count = len(games)
    if path == "":
        steps = "".join(f"<li>{escape(s)}</li>" for s in STEPS)
        body = (
            f"<h1>{SITE}!</h1><p>{escape(TAGLINE)}</p><p>{escape(SUMMARY)}</p>"
            f"<h2>How it works</h2><ol>{steps}</ol>"
            f"<h2>{count} games</h2>{_game_list(games, categories)}"
        )
        return f"{SITE}: party game show for friends", SUMMARY, _shell(body)
    if path == "games":
        body = f"<h1>All {count} games</h1><p>{escape(SUMMARY)}</p>{_game_list(games, categories)}"
        desc = f"Every Snazzlebop game with its rules: {count} party, quiz, bluffing and classic games."
        return f"All {count} games · {SITE}", desc, _shell(body)
    m = GAME_PATH.fullmatch(path)
    if m:
        g = next((x for x in games if x["id"] == m.group(1)), None)
        if g is None:
            return None
        steps = "".join(f"<li>{escape(s)}</li>" for s in g.get("how_to") or [])
        body = (
            f"<h1>{escape(g['title'])}</h1><p>{escape(g['blurb'])}</p>"
            f"<p>{_players(g)}. Free, in the browser: one person hosts, everyone else joins by phone.</p>"
            f"<h2>How to play</h2><ol>{steps}</ol><p>{_link('/', 'Host a room and play it')}</p>"
        )
        title = f"{g['title']}: how to play · {SITE}"
        return title, f"{g['blurb']} {_players(g)}, free in the browser.", _shell(body)
    simple = {
        "about": ("About", "Who makes Snazzlebop, why, and how to get in touch."),
        "plus": ("Snazzlebop Plus", "No ads, monthly coins and party items, every emote pack and a badge."),
        "terms": ("Terms", "The house rules: who can play, fair play, coins, Plus billing and refunds."),
        "privacy": ("Privacy", "What Snazzlebop keeps, why, for how long, and your rights."),
    }
    if path in simple:
        name, desc = simple[path]
        body = f"<h1>{escape(name)}</h1><p>{escape(desc)}</p><p>{escape(SUMMARY)}</p>"
        return f"{name} · {SITE}", desc, _shell(body)
    return None


def render(index_html: str, page: Page, canonical: str = "") -> str:
    """index.html with this page's title, description, its own address (canonical) and body in place."""
    title, desc, body = page
    if canonical:
        index_html = index_html.replace(
            "</head>", f'<link rel="canonical" href="{escape(canonical, quote=True)}" /></head>', 1
        )
    out = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", index_html, count=1, flags=re.S)
    out = re.sub(
        r'(<meta\s+name="description"\s+content=")[^"]*(")',
        lambda m: m.group(1) + escape(desc, quote=True) + m.group(2),
        out,
        count=1,
    )
    return re.sub(r'<div id="root">\s*</div>', lambda _m: f'<div id="root">{body}</div>', out, count=1)


def sitemap(site: str, games: Sequence[dict[str, Any]]) -> str:
    paths = ["", "games", "about", "plus", "terms", "privacy"] + [f"games/{g['id']}" for g in games]
    urls = "".join(f"<url><loc>{escape(site.rstrip('/'))}/{p}</loc></url>" for p in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
