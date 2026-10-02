I'm working in the Snazzlebop repo (party games: Frenemy Radar, Alibi, Price Is Weird). The scaffold is
complete and was authored in a sandbox with **no access to npm or PyPI**, so only the pure-Python
tests were ever run. Your job is to take it from "scaffolded and unit-tested" to "installed, running,
polished, secured and deployed on Render". Read `CLAUDE.md` and `SECURITY.md` first and treat the
"Architecture rules" in CLAUDE.md as inviolable.

## Phase 1: make it run (do this before anything else)
1. `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`.
   Fix anything the version ranges break. Then generate a **hash-locked** file
   (`pip-compile --generate-hashes` or `uv pip compile --generate-hashes`) and make the Dockerfile
   install from it with `--require-hashes`.
2. Run `pytest`, `ruff check .`, `ruff format .`, `bandit -q -r app -c pyproject.toml`, `pip-audit`.
   `tests/test_api.py` has never been executed: fix test or code as needed, but never weaken an
   assertion to make it pass. If a test reveals a real security bug, fix the code.
3. `cd frontend && npm install` (commit `package-lock.json`), `npm run typecheck`, `npm run build`.
   Fix type errors and any version drift in `package.json`.
4. Run both servers (`uvicorn app.main:create_app --factory --reload`, `npm run dev`) and play all three
   games end to end with 4-5 browser tabs. Fix every bug you hit.
5. `docker build -t snazzlebop .` and run it with `ENV=production`, a 40+ char `SECRET_KEY`,
   `ALLOWED_HOSTS=localhost`. Confirm `/healthz`, the SPA, a full game over WebSockets, the CSP header
   (check the browser console shows **zero** CSP violations, including fonts and WebSocket), and
   that `/docs` is 404.

## Phase 2: automated end-to-end + security verification
1. Write a Python script (`scripts/simulate.py`, uses `websockets` or httpx + starlette) that creates a
   room, joins 5 bots, and plays each game to completion, asserting scores update and secrets never
   appear in other players' frames. Run it in CI against the built container.
2. Write a load/abuse script (k6 or locust, in `scripts/loadtest/`) proving: room-creation flood from
   one IP gets 429; code-guessing gets 429; >12 sockets per IP are refused; a 50 msg/s socket is
   closed with 1008; oversized frames close with 1009; a client that never reads is dropped. Record
   the results in `docs/SECURITY-EVIDENCE.md` (what was run, what happened).
3. Run OWASP ZAP baseline against the container and fix or document every finding.
4. Add Playwright smoke tests (mobile 390px + desktop) for: home, create/join, lobby, each game's
   first screen. Use them for visual QA too.

## Phase 3: make the UI great (the product is the vibe)
Reference quality: my AniNest project (comic-book anime hub, github.com/MaXiMo000/AniNest) and my
Afterglow/portfolio sites: strong identity, hand-written CSS, accessible, no template look. Keep the
palette and type in `styles.css` but push it:
- Halftone/ink/hard-shadow comic language everywhere; per-game accent themes; punchy copy.
- Game-feel: animated phase transitions, a satisfying chaos-spin slot reveal in Price Is Weird,
  confetti/starburst on wins, "KAPOW"-style stingers on reveals, countdown pulse in the last 5 s,
  a shake on contradictions in Alibi, count-up on scores. Respect `prefers-reduced-motion`.
- Optional WebAudio sound effects (generated in code, **off by default**, toggle in the top bar;
  no audio files from third parties).
- A host "TV mode" (`/r/CODE?tv=1`, read-only big-screen view of the public state) is a stretch goal.
- Installable PWA (manifest + icons, same-origin only, no service-worker caching of `/api` or `/ws`).
- Lighthouse >= 95 on accessibility/best-practices/SEO, 44px touch targets, visible focus,
  screen-reader labels, keyboard-operable everything, contrast >= 4.5:1.

## Phase 4: gameplay depth (only after phases 1-3 are green)
- Price Is Weird: Sabotage token, a "Rigged Round", and a final Double-or-Nothing round.
- Alibi: tune difficulty with the simulator (killer should win roughly 35-45% of games with 5
  players); add a spectator-safe recap.
- Frenemy Radar: more prompts (keep them kind), a shareable result card rendered client-side.
- New games using the same engine: Telepathy Tax, Mole in the Mural. Each needs `view_for` secrecy
  tests before it ships.
- Host tools: kick player, lock room, rename room title. Reconnect UX polish.

## Phase 5: harden the pipeline, then deploy
1. Pin every GitHub Action in `.github/workflows/ci.yml` to a full commit SHA (tag in a comment),
   add a read-only default token, run carabiner-style checks if useful. Add `CODEOWNERS`.
2. Add Cloudflare notes to the README with the exact steps you verified; keep
   `TRUSTED_PROXY_HOPS` honest.
3. Deploy with the Render Blueprint (`render.yaml`). Walk the launch checklist in `SECURITY.md` against
   the **live URL** and tick each item only after observing it (curl the headers, try a foreign-origin
   WebSocket, confirm `/docs` is 404, run the abuse script against staging if allowed).
4. Update README with screenshots, the live URL, and what is and isn't verified.

## Ground rules
- Do not weaken any security control to make something easier. If a control is in your way, tell me
  and propose an alternative.
- No third-party requests from the browser, no inline scripts/styles, no `dangerouslySetInnerHTML`,
  no secrets in the repo, no logging of names/tokens/room codes.
- Game engines stay pure and tested. Keep tests fast and deterministic (inject clock + rng).
- Small commits with clear messages. Run the full test suite before each commit.
- Be honest in reports: state exactly what you ran and the result; never claim "fully secure". Say
  what remains (single instance, in-memory limits, no external review).

Start with Phase 1 now. Use a task list, and tell me when each phase is green.
