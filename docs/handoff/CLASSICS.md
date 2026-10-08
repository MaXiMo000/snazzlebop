# Handoff: the Classics (for the next chat)

Not production code. This is where a new session picks up the "add the classic games" project, what was
decided and why, and the mistakes already made so they aren't repeated. Read this first, then CLAUDE.md.

## The request (from the user)

Add 8 well-known games as "team games / classics", with rules like the originals, polished UI and
animations "with our website touch", built one at a time with a check-in after each:
Ludo, Monopoly, Uno, Chess, Wordle, Scribble, Gartic (Phone), Truth or Dare.

The user cares a lot about layout quality: **no awkward line breaks, no words split mid-word, no orphan
words, no text spilling out of boxes, nothing half-cut** at any phone width. They also asked for a
screenshot gallery of every phase on several devices before pushing.

## Status

| # | Name on the site | Original | State |
|---|---|---|---|
| 1 | Truth or Dare | Truth or Dare | done, pushed (`9cc670b`) |
| 2 | Word Race | Wordle | done (`638dee1`) |
| 3 | Last Card | Uno | done (`e48336b`) |
| - | polish from the screenshot pass | - | done (`8a58606`) |
| 4 | Ludo | Ludo | **next** |
| 5 | Chess | Chess | to do |
| 6 | Draw & Guess | Scribble / skribbl / Pictionary | to do (needs live drawing, see below) |
| 7 | Draw Telephone | Gartic Phone | to do (reuses the Draw & Guess canvas) |
| 8 | Property Tycoon | Monopoly | to do (biggest; party timer) |

Screenshot gallery of the three done games (private to the user):
https://claude.ai/artifact/VqZwALznGDnYX4HzjH3TeD

## Decisions (and why)

- **Names**: trademarked games get our own clear names (user chose "our names but better known,
  understandable"): Last Card, Word Race, Draw & Guess, Draw Telephone, Property Tycoon. Ludo, Chess,
  Truth or Dare keep their names. Rules must match the originals.
- **Lobby**: a new `Game.CLASSIC = True` flag (base.py) -> catalog field `classic` -> its own "The
  classics" section in the lobby (Room.tsx). Classics are also `SHOW = False` (never in show nights).
- **One game at a time**, check in with the user after each (their choice). Commit after each game;
  **push only when the user says so**.
- **Truth or Dare**: host picks heat Mild / Cheeky (Cheeky = bold and embarrassing, never sexual) and
  length (1/2/3 turns each). Truth 100, dare 200 if the room's majority votes thumbs-up (ties pass), +100
  Daredevil bonus from the 3rd dare in a row, one re-roll and one chicken-out per player. Prompts follow
  content.py's house rules (no bodies, money, identity, exes) and every dare works on a video call.
- **Word Race**: everyone races the same word; (7 - guesses) x 100, first solver +100, second +50; hard
  mode option; letters private until the reveal (others see colours only). Word lists in content.py
  (`WORD_ANSWERS`, `WORD_GUESSES`, `WORD_STEMS` plurals) via a `_words()` helper.
  **Open question for the user**: typing uses the device keyboard plus a display-only QWERTY colour
  board, because a 10-key row can't meet the project's 44px tap-target rule on a phone. Offer the user a
  tappable on-screen keyboard if they want it (it would need an exception to the 44px rule).
- **Last Card**: official Uno rules (108 cards, draw-then-play, Wild Draw Four legality + challenge,
  catch window until the next player acts, 2-player Reverse = Skip), stacking off by default (option),
  1 or 3 hands, 30 s turn clock. Wild / Wild Draw Four turned at the start go back (no dealer to pick).
  Played cards are public and named in the log (`base`, `value` on log entries).
- **Plans for the rest** (agreed in principle, not built):
  - Ludo: real 15x15 board, 4 tokens per colour, capture, safe squares, extra roll on 6, three 6s lose
    the turn; 5-8 players play as teams sharing a colour. Animated dice and token moves.
  - Chess: write our own move generator (do **not** add python-chess: GPL); full rules (castling, en
    passant, promotion, check/mate/stalemate, 50-move, threefold, insufficient material) + clocks.
    More than 2 players = two teams taking turns, teammates can suggest moves (arrows). Perft tests.
  - Draw & Guess / Draw Telephone: need live drawing. The hub sends a full snapshot per change and
    the socket limits are 2 KB per message and 8 messages/s (config.py). Plan: a new "ink" message:
    the client batches stroke points every ~200 ms; the server validates and relays deltas; the
    per-connection mailbox (rooms.py `_post`) must keep a pending snapshot plus queued ink deltas
    (a snapshot clears older deltas) so deltas are never dropped; snapshots still carry the full
    drawing for reconnects. Guesses are free text: validate like names (clean_name style).
  - Property Tycoon: our own board/space names and card text (no Monopoly text or art), full rules
    (buy, rent, sets, houses/hotels, mortgages, auctions, trading, jail, cards, bankruptcy) and a
    party-length timer (ends after N rounds or minutes, richest wins).

## Mistakes made (don't repeat them)

1. **Bash heredocs with quotes/backslashes failed silently** in this Windows Git-Bash tool ("unexpected
   EOF", or nothing written). Write content with the Write tool, or write a small Python script file and
   run it. For edits with backslashes use the Edit tool.
2. **Python `write_text` on Windows turns LF into CRLF.** Use `write_bytes(s.encode("utf-8"))`.
3. **uvicorn `--reload` on Windows did not reload** after an edit (old code kept running). Run without
   `--reload` and restart the API (preview_stop / preview_start) after every backend change.
4. **`view_for` crashed after the game ended** (Truth or Dare indexed past the last turn): unit tests
   didn't call `view_for` in the final phase. Always test `view_for` for players and a TV id **in every
   phase, including final**.
5. **Bot/test-driver bugs looked like game bugs**: bots acting on stale frames (sleeping inside the
   message loop) fell further behind until every turn timed out. Bots must handle frames without
   blocking and act on the *latest* state (see `LATEST` in tools/drive.py; scripts/simulate.py's Last
   Card bots sync on a state token before each move).
6. **Long sleeps in the driver** (`@9999` pace) blocked new commands; it now polls every 0.5 s.
7. **12 WebSockets per IP** (security cap): stale drivers + browser tabs got HTTP 403. Kill old drivers
   (match `drive.py` in the process command line; don't kill every python.exe, that hits the API).
8. **Playwright won't click pulsing buttons** (LAST CARD!, Catch): use `{ force: true }`.
9. **`grep -c` with zero matches exits 1** and silently stops an `&&` chain (a commit didn't happen).
10. **Lint/CI traps**: ruff line length 110; SIM905 (`"""...""".split()` -> use `_words()`); B023 (bind
    loop variables in lambdas); ASYNC240 (no Path work in async functions); **bandit fails on `assert`
    in app code** (use an explicit guard).
11. **Layout misses that only showed on real screens**: mid-word breaks in the bottle seats and the
    finale name, a 10-key keyboard can't be 44px, seats one-per-row pushing the hand off screen,
    phone-sized elements left tiny on laptop/TV, a TV card where a long name spilled into the next
    card, labels wrapping on 360px. **Check every new screen at 320/360/390px, a laptop and the TV view,
    with long names** ("Bartholomew X", "Alexandria Wood", 16 chars).
12. **No inline styles (CSP)**: positions like the bottle's seat angles are generated CSS rules keyed by
    data attributes, not `style=`.
13. Errors used to show at the top of the page, off-screen on phones; they are now a fixed toast
    (`.toast` in ui.tsx/styles.css). Server error messages are what players see: keep them short.

## Per-game checklist (what "done" means here)

1. Engine `backend/app/games/<id>.py` (pure; `HOW_TO`, `READING`, `OPTIONS`, `CLASSIC = True`,
   `SHOW = False`, highlights, summary) + content in content.py if needed.
2. `backend/tests/test_<id>.py`: rules, edge cases, timers/`advance()`, and secrecy for players + a
   `tv:` id + an `au:` id in every phase including final.
3. Register in `games/__init__.py`; add the id to the lists in `tests/test_api.py` and `tests/test_games.py`.
4. Frontend: id + view type in `types.ts`, `SEGMENT_ICON` in components/show.tsx, `GameRouter` case and
   `OPTION_LABELS` in pages/Room.tsx, screen `frontend/src/games/<Name>.tsx` (with `tv` read-only mode),
   styles in styles.css (`.seg-<id>` accent), colour pairs in `frontend/scripts/contrast.mjs`.
5. Home page list (pages/Home.tsx) and the game count ("Nineteen games." -> next number), README count,
   the games line in CLAUDE.md.
6. `scripts/simulate.py`: `play_<id>`, `ALLOWED_KEYS` per phase, score check, `EXPECTED_BY_GAME` for
   legitimately racy errors.
7. Checks: `ruff check . && ruff format --check .` (backend), the scripts lint, `bandit`, `pytest`,
   `npm run typecheck`, `npm run build`, `node scripts/contrast.mjs`, simulator against a local API
   (`--base http://localhost:8000 --only <id>`), then play it live at phone width with tools/drive.py,
   run axe in the page (load `/node_modules/axe-core/axe.min.js` via fetch + eval in the dev server)
   and the 44px target check, then the device gallery with tools/capture.cjs (extend it for the new game).
8. Commit (attribution line from the session). Push only when the user asks.

## Useful commands (Windows, from the repo root)

- API: `backend/.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --app-dir backend --port 8000`
  with env `JUMPSCARE=false` (the prank would scare test names otherwise).
- Web: `npm --prefix frontend run dev` (port 5173, proxies /api and /ws).
- Simulator: `backend/.venv/Scripts/python.exe scripts/simulate.py --base http://localhost:8000 --only lastcard --bots 4`
- e2e/Lighthouse need the Docker container on :10000 (not run locally this time; CI runs them).
