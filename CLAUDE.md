# Snazzlebop

Party games for friends in a browser (1-8 players plus an audience). One room code, no signup. Retro TV game-show UI, server-authoritative
games, security-first FastAPI backend, one Docker service on Render.

Games: **Frenemy Radar**, **Alibi**, **Price Is Weird**, **Telepathy Tax**, **Mole in the Mural**,
**Blackjack Showdown** (solo/side bets/chaos/tournament), **Crossword Race** (teams, bought letters),
**Liar's Dice**, **Split or Steal**, **Chicken Run**, **Wager Wits**, **Code Crackers**, **Roulette
Royale**, **Lowest Lonely Number**, **Mystery Box Auction**, the team game **Codewords** (`SHOW = False`:
played on its own, never in a show playlist) and the classics (`CLASSIC = True`, their own lobby section,
also `SHOW = False`): **Truth or Dare**, **Word Race** (Wordle-style), **Last Card** (Uno-style), **Ludo**. More classics are
planned in this order: Chess, Draw & Guess, Draw Telephone, Property Tycoon (Monopoly-style).
Trademarked originals get our own names; rules match the originals. **Work in progress: read
[docs/handoff/CLASSICS.md](docs/handoff/CLASSICS.md) first** (status, decisions, mistakes to avoid, the
per-game checklist and the dev tools in docs/handoff/tools/). Show nights (show.py): a playlist on one
scoreboard, host quips, highlight reel and awards, Jackpot finale, power cards (games expose `peek()`),
rivals, Friend Stock Exchange (shorts, dividends, insider tips), rematches and a season table, show
packs, audience (react, predict, trade, MVP vote), live reactions.

## Layout

```
backend/            FastAPI app (Python 3.13)
  app/
    main.py         app factory, routes, SPA hosting, middleware order
    config.py       Settings from env (production refuses weak/missing secrets)
    security.py     tokens, rate limiter, client IP, ASGI middleware (host/headers/body/rate)
    rooms.py        Hub + Room: lobby, message routing, broadcast, ticker, cleanup
    ws.py           WebSocket endpoint: origin, caps, auth handshake, flood limits
    db.py           optional anonymous stats (SQLAlchemy async; SQLite local, Postgres on Render)
    games/          base.py contract (+ Deck: per-room no-repeat dealing), content.py (all pools),
                    one module per game (pure Python), jackpot.py (show finale)
    show.py         show night: playlist, quips, awards, Friend Stock Exchange (pure)
    contentgen.py   optional Claude content: validate, de-dup, persist, grow pools; off without a key
  tests/            one file per game or feature (test_games, test_upgrades, test_show, test_dice, ...),
                    test_rooms / test_security + test_api
frontend/           Vite + React + TypeScript, hand-written CSS (game-show style), no UI library
  src/pages         Home, Room (join gate, lobby, game router, TV mode)
  src/games         one screen per game (each with a read-only TV variant)
  src/lib           api (fetch + session), useRoom (WebSocket hook + countdown), sfx (WebAudio)
  src/components    ui (cards, buttons, clock, scoreboard), fx (count-up, stingers, confetti)
  e2e/              Playwright smoke + axe + keyboard + TV tests (mobile 390px + desktop)
  scripts/          contrast.mjs, lighthouse.sh (Docker), icons.mjs
Dockerfile          builds frontend, serves it from FastAPI (same origin)
render.yaml         Render Blueprint: web service + private Postgres
SECURITY.md         threat model, controls, limits, launch checklist
```

## Run locally

```bash
# terminal 1: API on :8000
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env        # optional; dev works with no env at all
uvicorn app.main:create_app --factory --reload --port 8000

# terminal 2: UI on :5173 (proxies /api and /ws to :8000)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in several tabs (use a private window for a different "player": the seat
is stored per tab in `sessionStorage`).

## Test

```bash
cd backend && pytest                 # everything (needs fastapi + httpx)
cd backend && python -m unittest tests.test_games tests.test_rooms tests.test_security   # no deps
cd backend && ruff check . && ruff format --check . && bandit -q -r app -c pyproject.toml
cd frontend && npm run typecheck && npm run build && npm run contrast
cd frontend && npm run e2e                     # against a container on :10000
cd frontend && bash scripts/lighthouse.sh      # a11y/best-practices/SEO >= 95
python scripts/simulate.py                     # every game + secrecy checks over WS (--only dice ...)
python scripts/grow_pools.py                   # grow content pools with Claude (needs ANTHROPIC_API_KEY)
python scripts/tune_alibi.py                   # Alibi balance: killer should escape 35-45% at 5p
bash scripts/loadtest/run.sh                   # abuse suite (see docs/SECURITY-EVIDENCE.md)
```

## Deploy on Render

1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → select the repo. `SECRET_KEY` is generated, the database is
   wired in, the host/origin allowlists come from `RENDER_EXTERNAL_HOSTNAME`.
3. Open the service URL. Health check: `/healthz`.
4. Custom domain / Cloudflare: see "Client IP and Cloudflare" in [SECURITY.md](SECURITY.md).

Free web instances sleep when idle and drop live rooms; use the Starter plan for real play nights.

## Architecture rules (do not break these)

1. **Server-authoritative.** Clients send intents (`act`), never state. `Game.view_for(pid)` is the
   *only* way a game exposes data. Any secret (killer, fake slots, sealed price modifier, others'
   rankings) must be absent from other players' views until the reveal. Each game has tests for this.
2. **Game engines are pure** (no FastAPI, no I/O, injected `clock` and `rng`) so they stay testable.
3. **Every client input is validated** (`as_int`, strict list/str checks) and raises `GameError`.
   Never `eval`, never string-build SQL, never trust field names.
4. **No inline scripts or styles, no third-party requests.** CSP is `default-src 'none'` + `'self'`.
   Fonts are self-hosted via @fontsource. Do not add CDNs, analytics, or `dangerouslySetInnerHTML`.
5. **Token in the first WebSocket message**, never in a URL. Logs never contain names, tokens, codes.
6. **One worker.** Room state lives in memory and is snapshotted to Postgres after every change
   (`persist.py`, HMAC-signed pickles), so a restart or deploy doesn't end a game: rooms are restored on
   first use. Anything that needs scale-out goes behind `Hub` first. A room must stay picklable (no
   lambdas or live handles on games/shows; connections and locks are excluded in `Room.__getstate__`).
7. Adding a game: subclass `Game`, register in `games/__init__.py`, add a React screen + type,
   write `view_for` secrecy tests (players AND a TV spectator id), give it a TV (read-only) screen,
   add it to the lobby catalog (automatic via `catalog()`). Give it `HOW_TO` (plain rules, shown on the
   intro screen before it starts) and `READING` (results phases the room can skip together with Ready).
   Also: its `GameCard` id + view type in `types.ts`, a `SEGMENT_ICON`, a `.seg-<id>` accent (and its
   pairs in `scripts/contrast.mjs`), the registry lists in `test_api.py` / `test_games.py`, and a
   `play_<id>` in `scripts/simulate.py`.

## The prank (optional)

On by default (built-in names in `config.py`); `JUMPSCARE=false` turns it off and
`JUMPSCARE_NAMES=a,b,c` replaces the list. Test containers set `JUMPSCARE=false` (the e2e host is
called Ana). Matching players get a full-screen
ghost and a synthesised scream on arrival and on every score screen (`prank.py`, `JumpScare.tsx`,
`lib/scare.ts`). Matching forgives case, look-alike digits and one wrong letter. Only the target's own
view carries the `scare` counter. Ghosts and sound are generated on the device: nothing is downloaded.

## Conventions

- Python: typed, ruff-clean, `from __future__ import annotations`, small functions.
- TypeScript: `strict`, no `any`, styling only via classes + the CSS variables in `styles.css` (no `style=` props).
- UI: retro TV game show, NOT comic-book (no Bangers/halftone/KAPOW: that is the AniNest look). Bungee
  display + Fredoka body; cream/plum/tangerine/mustard/teal/cherry; marquee bulbs, sunburst, podium
  buttons, split-flap codes. Each game is a segment (`.seg-<id>` sets `--accent`). Dark theme is the
  default (`:root`), light is `:root[data-theme="light"]`: use the role tokens (`--bg`, `--surface`,
  `--ink`, `--muted`, `--edge`, `--shadow`, `--stage`, `--field`), not raw brand colours, for anything
  that should follow the theme. Effects respect
  `prefers-reduced-motion`; sounds are generated (`lib/sfx.ts`), off by default. 44px targets, visible
  focus, every control labelled, contrast >= 4.5:1 (`npm run contrast`).
- Content: big pools, no repeats within a room until a pool is exhausted (fun long-term). New content
  comes only through `contentgen.add_items` (validated); games must keep working with the key unset.
