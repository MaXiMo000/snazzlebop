# Security evidence

What was actually run against Snazzlebop, and what happened. Each claim below is something that was
observed, not assumed. Where a result has a caveat, the caveat is stated next to it.

**Run on:** 2026-10-02, Windows 11 + Docker Desktop (engine 29.7.2), production image built from the
working tree at `e0b1d45` plus the CI/doc commit that adds this file. Inside the image: Python 3.13.16,
uvicorn 0.54.0, FastAPI 0.142.2, Starlette 1.7.0.
**Not yet run against:** Render or Cloudflare. Everything here is a local container. The launch
checklist in [SECURITY.md](../SECURITY.md) still has to be walked against the live URL (Phase 5).

## How to reproduce

| What | Command | CI job |
| --- | --- | --- |
| Unit + API tests (136) | `cd backend && pytest` | `backend` |
| Full games, secrecy checks | `python scripts/simulate.py --base http://localhost:10000` | `docker` |
| Abuse suite (Locust) | `bash scripts/loadtest/run.sh` | `abuse` |
| OWASP ZAP baseline | see `docker` job in `.github/workflows/ci.yml` | `docker` |
| Browser smoke, mobile + desktop | `cd frontend && npm run e2e` (container on :10000) | `docker` |

The container was run with `ENV=production`, a 64-character `SECRET_KEY`, and `TRUSTED_PROXY_HOPS=0`.
Nothing sits in front of a local container, so trusting zero `X-Forwarded-For` hops is the honest
setting. On Render it is 1, and 2 behind Cloudflare.

## 1. Abuse suite (`scripts/loadtest/`)

Locust runs the scenarios below in order from **one client IP**. The suite runs in its own container
on a private Docker network with the app, not through Docker Desktop's host port proxy, because that
proxy reads eagerly on the client's behalf and would hide TCP backpressure.

Final run (all PASS, Locust exit code 0):

| # | Scenario | Expected (SECURITY.md) | Observed |
| --- | --- | --- | --- |
| 1 | Room of 8 sockets | 8 players play normally | 8/8 connected, played a Price round, all saw the reveal |
| 2 | >12 sockets per IP | refused | 12 accepted; the 13th was refused at the handshake (HTTP 403) |
| 3 | 50 msg/s on one socket | closed 1008 | closed with **1008** (limit is 8 msg/s, burst 16) |
| 4 | Oversized frames | closed 1009 | 3 KB (app limit 2 KB) → **1009** in 1 ms; 20 KB (uvicorn `--ws-max-size 16384`) → **1009** in 1 ms |
| 5 | Client that never reads | dropped | dropped after **18 s**; 3 readers kept playing (114 host msgs, ~118 frames each, 525 KB delivered); app log: `dropping unresponsive connection` |
| 6 | Room-creation flood | 429 | 429 from request 6 of 20 (15 refused), `Retry-After: 10` |
| 7 | Code guessing | 429 | `[404, 404, 404, 429]`: 429 from guess 4; that IP's join to a *real* room then got 429 and its socket was refused (HTTP 403) |

Caveats:
- **Scenario 4 (20 KB):** uvicorn rejects the frame from its header and sends 1009, then closes with
  the unread payload still queued. The kernel may answer with a TCP reset that overtakes the close
  frame, and the client then sees 1006. One of three runs showed 1006. The suite accepts 1006 for this
  case only if the socket was gone within 2 s.
- **Scenario 5:** with a 4 KB client receive buffer, the drop took 18-40 s depending on how fast
  buffers filled. A client that never reads is also cut off by uvicorn's keepalive after about 40 s
  (ping every 20 s, 20 s pong timeout), whichever comes first.
- **Scenarios 2 and 7:** the refusal happens before the WebSocket is accepted, so a browser sees a
  failed handshake (1006), not a close code.

### Bugs these runs found (all fixed, each with a regression test)

| Found by | Problem | Fix |
| --- | --- | --- |
| abuse suite, scenario 5 | `broadcast()` awaited every recipient, so while one non-reading socket's buffers were full, **every player's actions were delayed up to 5 s per broadcast**: 182 host messages arrived as about 86 frames per reader. The drop was also logged and closed 8 times. | One-slot mailbox per connection: frames are full snapshots, so a busy socket just gets the newest state next and broadcasters never wait on it. It is dropped once. `test_stuck_reader_never_stalls_the_room` |
| manual review during Phase 1 play | `/ws/<CODE>` accepted real rooms and refused unknown ones before auth, with no rate limit: **a free oracle for valid room codes** that bypassed the join penalty | Unknown room now fails at auth exactly like a bad token (1008). Handshakes count against the per-IP bucket, and a failed auth with a forged or foreign token costs 4 join tokens. `test_ws_room_guessing_is_indistinguishable_and_penalised` |
| first version of the above | It also penalised genuine tokens for rooms that had ended, so **a party on one NAT locked itself out after a restart** | Only tokens not signed for this code are penalised. `test_ws_stale_but_genuine_token_is_not_penalised` |
| container log review | uvicorn logs `"WebSocket /ws/<CODE>" [accepted]` with the client IP on `uvicorn.error`, which `--no-access-log` does not cover: **room codes and IPs in production logs** | Logging filter drops those lines. Verified: container logs after full games contain no room code. |
| container `curl` | `/docs` and `/openapi.json` returned **200** (the SPA catch-all served `index.html`). The test only passed because it had no built SPA. | Catch-all serves `index.html` only for `/` and `/r/<code>`; the test now uses a built SPA. |

## 2. End-to-end simulator (`scripts/simulate.py`)

A host and 3-7 bots play Frenemy Radar, Alibi and Price Is Weird over real HTTP and WebSockets.
Every frame each bot receives is checked:

- per-phase whitelist of view fields;
- each bot's price guesses (and hedges) compared by exact value against every other bot's frames
  before the reveal;
- exactly one bot is told it is the killer, and no innocent ever gets `fake_slots`;
- the final truth table matches every innocent's card, and the killer's card differs only at the fake
  slots;
- the Price seal: `sha256(modifier:nonce)` equals the commitment shown before guessing;
- session scores rise after every game, and no unexpected error codes appear.

Result: all games pass for 3-7 bots across 12 seeds, about 11 s per run. A 5-bot run checked 132
Frenemy, 234 Alibi and 216 Price frames, with 32 planted guesses never leaked.

**The checks were themselves tested:** the simulator was pointed at a server patched to leak
(a) everyone's price guesses, (b) Alibi fake slots to innocents, (c) Frenemy rankings during ranking.
All three runs failed with the right message.

Found along the way: the bots initially sent about 30 messages in 2 s and the host was closed with
1008 by the per-socket limit. The limit was working, so the bots are now paced at 5 msg/s. A substring
leak check also gave a false positive (a guess like `501000` inside a `remaining` float), so it was
replaced with exact-value matching. The simulator also showed the Price UI printing the proof as
`sha256("1:…")` while the server hashes `"1.0:…"`, which would make an honest spin look rigged. Fixed.

## 3. OWASP ZAP baseline

`zap-baseline.py` (ZAP 2.17.0, image `ghcr.io/zaproxy/zaproxy@sha256:781a2bda…`) against the
production container.

First run: 0 FAIL, 65 PASS, 2 WARN.

| Alert | Risk | Disposition |
| --- | --- | --- |
| 90004 Cross-Origin-Embedder-Policy missing | Low | **Fixed:** `COEP: require-corp`. Everything is same-origin; verified the built app is `crossOriginIsolated` with fonts and WebSocket working. |
| 10049 Storable and cacheable content (`/assets/*`, `/`, 404s) | Informational | Intended: hashed assets are `immutable`; `index.html` is `no-cache` (always revalidated). JSON error bodies now send `no-store`. |

Second run: 0 FAIL, 65 PASS. Remaining alerts are all Informational:
- 10049 cacheability notes (as above, intended);
- 10109 "Modern Web Application" (a hint to use the AJAX spider; there is no server-rendered content to
  find).

ZAP baseline is a passive scan of HTTP responses. It does not exercise WebSockets, which is where the
game logic lives; that is covered by sections 1 and 2 and `tests/test_api.py`.

## 4. Browser smoke tests (Playwright)

`frontend/e2e/smoke.spec.ts`, Chromium, at 390×844 (mobile, touch) and 1280×800. Four players in
separate contexts: home → create → join by code form → join by invite link → lobby (4 online) → first
screen of each game, then the host skips each game through to results. Any console error or CSP
violation fails the test. Screenshots per step are saved for visual QA (CI artifact
`playwright-screenshots`).

Result: 2/2 pass. The first run failed on mobile: the 7-column Alibi truth table overflowed its panel
at 390 px and covered the "Play another game" button. Fixed with a focusable, labelled scroll region
around the table.

## 5. Phase 4 additions (re-run after the new games, host tools and TV mode)

- **Backend:** 106 tests pass, including `view_for` secrecy for every game against a TV spectator id,
  Telepathy and Mural rules and secrecy, host tools, and the TV read-only/cap/eviction rules.
- **Simulator:** now plays all five games. New checks:
  - Telepathy picks only ever reach their owner, and points are recomputed from the rules.
  - Mural: exactly one Mole, the Mole never receives the painting, every innocent gets the same one.
  - Price: sabotage and double-or-nothing appear only in their owner's frames; each player's points
    are recomputed from the revealed history and must match the scoreboard exactly.
  - Passed for 3, 5 and 7 bots across several seeds.
- **Abuse suite:** 7/7 pass again on the final image (slow reader dropped after 16 s while the room kept
  playing).
- **Lighthouse:** home is 100/100/100 (a11y/best practices/SEO); room pages are noindex by design.
- **Playwright:** 14 tests across mobile and desktop. They add Telepathy and Mural, TV mode, host
  tools (rename/lock/kick with axe), reconnect after a dropped socket, the share card, and reduced motion.
- **Alibi balance** (`scripts/tune_alibi.py`, 5,000 games per size, simple human-like bots): the killer
  escaped 12% at 5 players before the change and 37-43% at 4-8 players after it (37-38% at 5). Bots are
  a model of play, not people: real tables will vary.

## 6. Blackjack, Crossword, Claude content, supply chain (run 2026-10-03)

- **Backend:** 136 tests. New coverage:
  - Blackjack: a 300-game fuzz checks chip conservation and that the hole card and shoe never reach a
    view before the reveal.
  - Crossword: 200 generated grids checked for legality; unsolved answers never appear in a view.
  - Content generation (stubbed client): validation per kind, de-duplication, the hourly budget and
    backoff, refusal handling, persistence across restarts, and committed extras going through the
    same validator.
  - Edge secret: requests without the CDN header are refused, and production won't start with 2 hops
    and no secret.
- **Simulator:** all seven games pass with 5 bots against the final image.
  - Blackjack: no frame shows more than one dealer card before settling, and chip changes equal the
    reported net.
  - Crossword: no unsolved answer ever appears, a wrong guess is rejected, and the answers are
    revealed at the end.
- **Playwright:** 14/14 on the final image. Reviewing its screenshots found a real bug: the lobby
  card's bare `mural` class pulled in the tile grid and squashed the card on phones. Fixed in `454144d`.
- **Claude content:**
  - Generated text is validated and length-capped before it joins a pool.
  - It's rendered by React as text (no HTML), so a hostile completion can at worst be odd words on
    screen.
  - The key is `repr=False` and is never logged; failures log only the exception type.
  - **Not run against the real API**: no key has been used yet.
- **Image:**
  - Trivy (`aquasec/trivy` v0.75.0, pinned by digest), CRITICAL/HIGH with a fix available: **0**.
  - The first scan found 1 Debian HIGH (libpcre2) and 4 HIGH in pip's vendored urllib3/msgpack and in
    setuptools. The fix: apply Debian security updates at build time, and remove pip, setuptools and
    wheel from the runtime image (nothing installs at runtime).
- **CI supply chain:**
  - Every action is pinned to a commit SHA (`carabiner fix`), checkouts set `persist-credentials:
    false`, and the default token is read-only.
  - The old `aquasecurity/trivy-action@0.28.0` ref never existed, so the docker job could not have
    passed; it's replaced by the digest-pinned image.
  - `carabiner scan`: one informational finding (`*.pem`/`*.key` not gitignored), now fixed.
  - gitleaks v8.28.0 over all 29 commits: no leaks.
- **Abuse suite:** 7/7 pass on the final image (13th socket 403, flood 1008, oversize 1009 in 1 ms,
  slow reader dropped after 15 s while the room played on, create flood 429 from #6, code guessing 429
  from #4).

- **GitHub Actions:** first run on `97fb8de` (run 37071029873) passed every job: backend, frontend,
  docker (Trivy, simulator, Playwright, Lighthouse, ZAP), abuse, secrets, CodeQL x2.

## What is not covered (be honest)

- **Single instance, in-memory limits.** Rate limits and rooms reset on restart and are per process.
- **One client IP.** A botnet with many IPs is out of scope for app-level limits. The answer there is
  Cloudflare (WAF rate rules, Bot Fight Mode, optionally Turnstile on room creation), and none of that
  is set up or tested yet.
- **No volumetric DDoS testing**, and none would be meaningful against a laptop.
- **Not run against Render or Cloudflare.** `TRUSTED_PROXY_HOPS=1` (Render) and `2` (Cloudflare +
  `EDGE_SECRET`) are untested against the real proxies. SECURITY.md "Edge setup" step 7 is the check.
- **No external review or penetration test.** Treat this as a strong, evidenced baseline, not a
  certification.
