import html
import json
import pathlib

# Dev tool (not production). usage: python make_gallery.py <gallery dir written by capture.cjs>
# Writes <dir>/index.html (Snazzlebop-styled contact sheet); move the .jpg files into <dir>/shots/.
G = pathlib.Path(__import__("sys").argv[1])
shots = json.loads((G / "manifest.json").read_text(encoding="utf-8"))

GAMES = [
    ("lobby", "The lobby", "Where the new games live: the Classics section."),
    ("truthdare", "Truth or Dare", "Spin the bottle, pick a door, do it, and the room votes."),
    ("wordrace", "Word Race", "Wordle rules, but everyone races the same word."),
    ("lastcard", "Last Card", "Uno rules: match, skip, reverse, draw four, call LAST CARD!"),
]
ORDER = ["laptop", "phone", "tablet", "small", "tv"]
SHORT = {"laptop": "Laptop", "phone": "Phone", "tablet": "Tablet", "small": "Small phone", "tv": "TV"}
DETAIL = {
    "laptop": "1366px · light",
    "phone": "390px · dark",
    "tablet": "820px · dark",
    "small": "360px · light",
    "tv": "1920px",
}

sections = []
nav = []
total = 0
for gid, name, blurb in GAMES:
    mine = [s for s in shots if s["game"] == gid]
    if not mine:
        continue
    steps: list[str] = []
    for s in mine:
        if s["step"] not in steps:
            steps.append(s["step"])
    nav.append(f'<a class="nav-chip" href="#{gid}">{html.escape(name)}</a>')
    rows = []
    for i, step in enumerate(steps, 1):
        group = sorted((s for s in mine if s["step"] == step), key=lambda s: ORDER.index(s["device"]))
        total += len(group)
        title = group[0]["title"]
        figs = []
        for s in group:
            alt = f"{name}, {title}, on the {SHORT[s['device']].lower()}"
            figs.append(
                f'<figure class="shot d-{s["device"]}">'
                f'<a href="shots/{s["file"]}" target="_blank" rel="noopener" aria-label="Open full size: {html.escape(alt)}">'
                f'<img src="shots/{s["file"]}" alt="{html.escape(alt)}" loading="lazy"></a>'
                f'<figcaption><b>{SHORT[s["device"]]}</b><span>{DETAIL[s["device"]]}</span></figcaption></figure>'
            )
        rows.append(
            f'<article class="phase"><header class="phase-head"><span class="step">Phase {i}</span>'
            f'<h3>{html.escape(title)}</h3></header>'
            f'<div class="strip" tabindex="0" role="region" aria-label="{html.escape(title)}: screenshots">{"".join(figs)}</div></article>'
        )
    sections.append(
        f'<section class="game g-{gid}" id="{gid}"><div class="game-head"><h2>{html.escape(name)}</h2>'
        f'<p>{html.escape(blurb)}</p></div>{"".join(rows)}</section>'
    )

page = f"""<title>Snazzlebop Classics Preview</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bungee&family=Fredoka:wght@400;500;600;700&display=swap">
<style>
/* Layout: one long contact sheet. Each game is a lit stage; each phase is a strip of device shots that
   scrolls sideways on its own, never the page. Snazzlebop's own palette: studio plum, cream, tangerine. */
:root {{
  --bg: #140b1b;
  --surface: #221530;
  --ink: #fff1dc;
  --muted: #cdb6d6;
  --edge: #5e4070;
  --bulb: #ffe7a1;
  --accent: #ff6b2c;
  --shadow: #05020a;
  --display: "Bungee", "Arial Black", Impact, sans-serif;
  --body: "Fredoka", ui-rounded, "Segoe UI", system-ui, sans-serif;
  color-scheme: dark;
}}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{
    --bg: #fff1dc; --surface: #fffaf1; --ink: #2b1b33; --muted: #6b4f73; --edge: #2b1b33;
    --bulb: #ffe7a1; --accent: #c4471a; --shadow: #2b1b33; color-scheme: light;
  }}
}}
:root[data-theme="light"] {{
  --bg: #fff1dc; --surface: #fffaf1; --ink: #2b1b33; --muted: #6b4f73; --edge: #2b1b33;
  --bulb: #ffe7a1; --accent: #c4471a; --shadow: #2b1b33; color-scheme: light;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding-inline: 16px;
  padding-block: 28px 64px;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--body);
  font-size: 1rem;
  line-height: 1.5;
}}
.wrap {{ max-width: 1200px; margin: 0 auto; display: grid; gap: 40px; }}
.intro {{ display: grid; gap: 14px; max-width: 70ch; }}
.sign {{
  justify-self: start;
  padding: 4px 14px;
  font-family: var(--display);
  font-size: 0.8rem;
  letter-spacing: 0.08em;
  color: #2b1b33;
  background: var(--bulb);
  border: 3px solid var(--edge);
  border-radius: 10px;
}}
h1 {{ margin: 0; font-family: var(--display); font-weight: 400; font-size: clamp(2rem, 7vw, 3.4rem); line-height: 1.05; text-wrap: balance; }}
h1 span {{ color: var(--accent); }}
.intro p {{ margin: 0; color: var(--muted); text-wrap: pretty; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; }}
.legend li {{ padding: 4px 12px; font-weight: 600; font-size: 0.9rem; border: 2px solid var(--edge); border-radius: 999px; }}
nav {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.nav-chip {{
  display: inline-flex; align-items: center; min-height: 44px; padding: 8px 18px;
  font-family: var(--display); font-size: 0.85rem; letter-spacing: 0.03em; text-decoration: none;
  color: var(--ink); background: var(--surface); border: 3px solid var(--edge); border-radius: 999px;
  box-shadow: 0 4px 0 var(--shadow);
}}
.nav-chip:hover, .nav-chip:focus-visible {{ background: var(--accent); color: #fff; outline: none; }}
.game {{ display: grid; gap: 22px; scroll-margin-top: 16px; }}
.game-head {{ display: grid; gap: 4px; padding-bottom: 10px; border-bottom: 3px solid var(--edge); }}
.game-head h2 {{ margin: 0; font-family: var(--display); font-weight: 400; font-size: clamp(1.5rem, 5vw, 2.2rem); color: var(--accent); }}
.game-head p {{ margin: 0; color: var(--muted); }}
.phase {{ display: grid; gap: 10px; min-width: 0; }}
.phase-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; }}
.step {{ font-family: var(--display); font-size: 0.75rem; letter-spacing: 0.08em; color: var(--muted); font-variant-numeric: tabular-nums; }}
.phase h3 {{ margin: 0; font-size: 1.1rem; font-weight: 700; text-wrap: balance; }}
.strip {{
  display: flex; gap: 14px; overflow-x: auto; padding: 4px 4px 14px;
  scroll-snap-type: x proximity; overscroll-behavior-x: contain;
}}
.strip:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 2px; border-radius: 12px; }}
.shot {{ flex: 0 0 auto; margin: 0; display: grid; gap: 6px; scroll-snap-align: start; }}
.shot a {{
  display: block; height: 460px; overflow: hidden; border: 3px solid var(--edge); border-radius: 14px;
  background: var(--surface); box-shadow: 0 5px 0 var(--shadow);
}}
.shot a:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 3px; }}
.shot img {{ display: block; width: 100%; height: 100%; object-fit: cover; object-position: top; }}
.d-laptop a, .d-tv a {{ width: min(78vw, 440px); }}
.d-laptop a {{ height: auto; aspect-ratio: 1366 / 900; }}
.d-tv a {{ height: auto; aspect-ratio: 16 / 9; }}
.d-tablet a {{ width: 250px; }}
.d-phone a {{ width: 205px; }}
.d-small a {{ width: 190px; }}
figcaption {{ display: flex; flex-wrap: wrap; gap: 0 8px; font-size: 0.85rem; }}
figcaption span {{ color: var(--muted); }}
footer {{ color: var(--muted); font-size: 0.9rem; }}
@media (prefers-reduced-motion: no-preference) {{ html {{ scroll-behavior: smooth; }} }}
</style>
<div class="wrap">
  <header class="intro">
    <span class="sign">Preview before pushing</span>
    <h1>The three new <span>classics</span>, every phase, every screen</h1>
    <p>Real games played by four people at once in real browsers: Ana hosts on a laptop, Bartholomew X on a phone,
    Zara on a tablet and Leo on a small phone, with the living-room TV screen alongside. {total} screenshots.
    Each row is one moment of the game; swipe sideways for the other devices and tap any shot to open it full size.</p>
    <ul class="legend" aria-label="Devices">
      <li>Laptop · 1366px · light</li><li>Phone · 390px · dark</li><li>Tablet · 820px · dark</li>
      <li>Small phone · 360px · light</li><li>TV · 1920px</li>
    </ul>
    <nav aria-label="Games">{"".join(nav)}</nav>
  </header>
  {"".join(sections)}
  <footer>Phone shots are full-length pages: the thumbnail shows the top, tap it to see the whole screen.</footer>
</div>
"""
(G / "index.html").write_text(page, encoding="utf-8")
files = sorted(p.name for p in G.glob("*.jpg"))
(G / "files.json").write_text(json.dumps({f"shots/{f}": f for f in files}), encoding="utf-8")
print(total, "shots,", len(files), "files")
