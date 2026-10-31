"""Server-written HTML for the public pages: a real title, description and readable text in the very
first response, plus link-preview tags (Open Graph) and structured data (schema.org JSON-LD), so search,
ad and link-preview crawlers understand the page even before (or without) its JavaScript. The app
replaces the body when it starts. Pure: the game catalogue is passed in; everything from it is escaped.
"""

from __future__ import annotations

import json
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
HOME_DESC = (
    "Free online party games to play with friends: trivia, drawing, bluffing, Ludo, chess, Wordle-style "
    "races and 30+ more. One room code, everyone plays on their phone, put it on the TV. No download."
)
STEPS = (
    "Host a room: type your name and get a five-letter code.",
    "Friends join on their phones with the code or the invite link. Put the show on a TV if you like.",
    "Pick a game. Each one teaches its rules in a few seconds, then the show keeps score.",
)
# What each shelf is called in searches (the words people type), for titles and structured data.
GENRE = {
    "party": "party game",
    "quiz": "quiz and word game",
    "bluff": "bluffing game",
    "nerve": "game show game",
    "classics": "classic game",
}
# Each shelf's page title, in the words people search with.
SHELF_NAME = {
    "party": "Party Games",
    "quiz": "Quiz and Word Games",
    "bluff": "Bluffing and Social Deduction Games",
    "nerve": "Game Show Games",
    "classics": "Classic Board and Card Games",
}
OG_IMAGE = "/og.png"  # 1200x630, the link preview
GAME_PATH = re.compile(r"games/([a-z0-9]{2,24})/?")

# title, description, body HTML, structured data (schema.org objects)
Page = tuple[str, str, str, list[dict[str, Any]]]


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
        head = _link(f"/games/{cat['id']}", cat["title"])
        parts.append(f"<h3>{head}</h3><p>{escape(cat['blurb'])}</p><ul>{items}</ul>")
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
            ("/refunds", "Refunds"),
            ("/privacy", "Privacy"),
        )
    )
    return f'<div class="prerender prose-page"><nav aria-label="Site">{links}</nav>{body}</div>'


def _game_data(g: dict[str, Any], url: str) -> dict[str, Any]:
    return {
        "@type": "VideoGame",
        "name": g["title"],
        "url": url,
        "description": g["blurb"],
        "genre": GENRE.get(str(g.get("category")), "party game"),
        "playMode": "MultiPlayer",
        "gamePlatform": "Web browser",
        "applicationCategory": "Game",
        "operatingSystem": "Any (web browser)",
        "numberOfPlayers": {
            "@type": "QuantitativeValue",
            "minValue": g["min_players"],
            "maxValue": g["max_players"],
        },
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        **({"alternateName": [g["search"], *g["aka"]]} if g.get("aka") else {}),
    }


def _crumbs(*steps: tuple[str, str]) -> dict[str, Any]:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(steps)
        ],
    }


def page_for(
    path: str, games: Sequence[dict[str, Any]], categories: Sequence[dict[str, str]], site: str = ""
) -> Page | None:
    """The title, description, body and structured data for a public page, or None to leave the page
    as it is (rooms and signed-in pages: nothing for a crawler there)."""
    path = path.strip("/")
    base = site.rstrip("/")
    count = len(games)
    if path == "":
        steps = "".join(f"<li>{escape(s)}</li>" for s in STEPS)
        body = (
            f"<h1>{SITE}! Free party games to play with friends</h1><p>{escape(TAGLINE)}</p>"
            f"<p>{escape(SUMMARY)}</p><h2>How it works</h2><ol>{steps}</ol>"
            f"<h2>{count} games</h2>{_game_list(games, categories)}"
        )
        data = [
            {"@type": "WebSite", "name": SITE, "url": f"{base}/", "description": HOME_DESC},
            {"@type": "Organization", "name": SITE, "url": f"{base}/", "logo": f"{base}/icon-512.png"},
            {
                "@type": "ItemList",
                "name": "Snazzlebop games",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{base}/games/{g['id']}",
                        "name": g["title"],
                    }
                    for i, g in enumerate(games)
                ],
            },
        ]
        return f"{SITE}: Free Party Games to Play With Friends Online", HOME_DESC, _shell(body), data
    if path == "games":
        body = f"<h1>All {count} games</h1><p>{escape(SUMMARY)}</p>{_game_list(games, categories)}"
        desc = (
            f"All {count} Snazzlebop games and their rules: free online party, quiz, bluffing and classics."
        )
        crumbs = _crumbs(("Play", f"{base}/"), ("All games", f"{base}/games"))
        return f"All {count} Free Party Games Online · {SITE}", desc, _shell(body), [crumbs]
    m = GAME_PATH.fullmatch(path)
    if m:
        key = m.group(1)
        cat = next((c for c in categories if c["id"] == key), None)
        if cat is not None:
            rows = [g for g in games if g.get("category") == key]
            items = "".join(
                f"<li>{_link('/games/' + g['id'], g['title'])}: {escape(g['blurb'])} ({_players(g)})</li>"
                for g in rows
            )
            name = SHELF_NAME.get(key, cat["title"])
            title = f"Free {name} to Play Online With Friends · {SITE}"
            genre = GENRE.get(key, "party game")
            desc = f"{cat['blurb']} {len(rows)} free {genre}s to play online with friends."
            heading = f"<h1>Free {escape(name)} to play online with friends</h1>"
            body = f"{heading}<p>{escape(desc)}</p><ul>{items}</ul>"
            data = [
                _crumbs(
                    ("Play", f"{base}/"),
                    ("All games", f"{base}/games"),
                    (cat["title"], f"{base}/games/{key}"),
                ),
                {
                    "@type": "ItemList",
                    "name": cat["title"],
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": i + 1,
                            "url": f"{base}/games/{g['id']}",
                            "name": g["title"],
                        }
                        for i, g in enumerate(rows)
                    ],
                },
            ]
            return title, desc, _shell(body), data
        g = next((x for x in games if x["id"] == key), None)
        if g is None:
            return None
        genre = GENRE.get(str(g.get("category")), "party game")
        steps = "".join(f"<li>{escape(s)}</li>" for s in g.get("how_to") or [])
        search = str(g.get("search") or g["title"])
        aka = [str(a) for a in g.get("aka") or []]
        players = _players(g)
        also = f"<p>Also known as: {escape(', '.join(aka))}.</p>" if aka else ""
        body = (
            f"<h1>Play {escape(search)} online with friends, free</h1>"
            f"<p>{escape(g['title'])}: {escape(g['blurb'])}</p>{also}"
            f"<p>{players}. A free online {escape(genre)} in the browser: one person hosts, everyone else "
            "joins by phone.</p>"
            f"<h2>How to play</h2><ol>{steps}</ol>"
            f"<h2>How do I play {escape(search)} online with friends?</h2>"
            "<p>Open snazzlebop.com, host a room and share the five-letter code or the invite link. "
            f"Everyone joins on their phone, and the host picks {escape(g['title'])}. "
            "Put the show on a TV if you like.</p>"
            f"<h2>Is it free?</h2><p>Yes: free, no download and no sign-up. {players}.</p>"
            f"<p>{_link('/', 'Host a room and play it')}</p>"
        )
        lead = f"Play {search} Online Free With Friends"
        named = g["title"].lower() in search.lower()
        title = f"{lead} · {SITE}" if named else f"{lead}: {g['title']} · {SITE}"
        desc = f"Play {search} online free with friends: {players}, no download, no sign-up. {g['blurb']}"
        url = f"{base}/games/{key}"
        data = [
            _game_data(g, url),
            _crumbs(("Play", f"{base}/"), ("All games", f"{base}/games"), (g["title"], url)),
        ]
        return title, desc, _shell(body), data
    simple = {
        "about": (
            "About",
            "Who makes Snazzlebop, a free online party game show for friends, and how to reach us.",
        ),
        "plus": ("Snazzlebop Plus", "No ads, monthly coins and party items, every emote pack and a badge."),
        "terms": (
            "Terms",
            "The house rules: who can play, fair play, coins and coin packs, Plus billing and refunds.",
        ),
        "refunds": (
            "Refunds",
            "Any payment, for Plus or a coin pack, back in full within 14 days, no questions asked.",
        ),
        "privacy": ("Privacy", "What Snazzlebop keeps, why, for how long, and your rights."),
    }
    if path in simple:
        name, desc = simple[path]
        body = f"<h1>{escape(name)}</h1><p>{escape(desc)}</p><p>{escape(SUMMARY)}</p>"
        return f"{name} · {SITE}", desc, _shell(body), []
    return None


def _ld(data: list[dict[str, Any]]) -> str:
    """JSON-LD as a data block (not run as a script, so the Content Security Policy doesn't apply);
    "<" is escaped so no value can close the element early."""
    if not data:
        return ""
    doc = json.dumps({"@context": "https://schema.org", "@graph": data}, ensure_ascii=False)
    return '<script type="application/ld+json">' + doc.replace("<", "\\u003c") + "</script>"


def render(index_html: str, page: Page, canonical: str = "", site: str = "") -> str:
    """index.html with this page's title, description, address, link preview, structured data and body."""
    title, desc, body, data = page
    t, d = escape(title, quote=True), escape(desc, quote=True)
    head = [
        f'<meta property="og:type" content="website" /><meta property="og:site_name" content="{SITE}" />',
        f'<meta property="og:title" content="{t}" /><meta property="og:description" content="{d}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{t}" />',
        f'<meta name="twitter:description" content="{d}" />',
    ]
    if canonical:
        c = escape(canonical, quote=True)
        head.append(f'<link rel="canonical" href="{c}" /><meta property="og:url" content="{c}" />')
    if site:
        img = escape(site.rstrip("/") + OG_IMAGE, quote=True)
        head.append(
            f'<meta property="og:image" content="{img}" /><meta property="og:image:width" content="1200" />'
            f'<meta property="og:image:height" content="630" /><meta name="twitter:image" content="{img}" />'
        )
    head.append(_ld(data))
    index_html = index_html.replace("</head>", "".join(head) + "</head>", 1)
    out = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", index_html, count=1, flags=re.S)
    out = re.sub(
        r'(<meta\s+name="description"\s+content=")[^"]*(")',
        lambda m: m.group(1) + d + m.group(2),
        out,
        count=1,
    )
    return re.sub(r'<div id="root">\s*</div>', lambda _m: f'<div id="root">{body}</div>', out, count=1)


def sitemap(site: str, games: Sequence[dict[str, Any]], categories: Sequence[dict[str, str]] = ()) -> str:
    pages = ["", "games", "about", "plus", "terms", "refunds", "privacy"]
    paths = pages + [f"games/{c['id']}" for c in categories] + [f"games/{g['id']}" for g in games]
    urls = "".join(f"<url><loc>{escape(site.rstrip('/'))}/{p}</loc></url>" for p in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
