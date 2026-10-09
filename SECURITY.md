# Security

Snazzlebop is a small party-game server: anonymous players, short-lived rooms, no accounts, no passwords,
no payment data, no personal data beyond a display name that lives for the life of a room (in memory, and in
its database snapshot).
That shape removes most of the usual attack surface. This document says what is defended, how, and
what is **not** covered.

## Be honest about "fully protected"

No application is "fully" protected. What this repo does is layer defences and make every limit
explicit. In particular:

- **Volumetric DDoS (network-level floods) cannot be stopped by application code.** Render provides
  baseline platform protection (its edge is Cloudflare); for WAF and bot rules of your own, put your
  own Cloudflare zone in front. See "Client IP and Cloudflare".
- The app-level limits below stop *abuse of this app* (room spam, message floods, code guessing, slow
  or hostile clients, memory exhaustion), which is what a single machine can actually defend.
- No independent security review has been done. Treat this as a strong baseline, not a certification.

## Threat model

| Threat | Control |
| --- | --- |
| Cross-site WebSocket hijacking | `Origin` must be on the allowlist; in production a missing `Origin` is refused. Auth token travels in the first WS message, never in the URL. |
| Forged / replayed identity | Player tokens are HMAC-SHA256 signed (`SECRET_KEY`), bound to one room and one player, expire after 12 h, compared in constant time. The server re-checks the player exists in the room. |
| Room-code guessing | 5 letters from a 24-letter alphabet (~8M codes), `secrets`-generated, tighter join bucket, and every wrong code *penalises* the caller's rate-limit bucket. |
| Request / connection floods | Per-IP token buckets (default, create-room, join), per-IP and global WebSocket caps, per-connection message rate limit, 2 KB WS message cap, 4 KB HTTP body cap, 5 s auth deadline, 90 s idle timeout, 5 s send timeout (slow-reader defence), drawing strokes validated per op (canvas bounds, 60 points/op, 4000 ops / 60k points per canvas, artist only) with a 300-frame relay backlog per screen before it is told to redraw, uvicorn concurrency and keep-alive limits. |
| Memory exhaustion | Max rooms, max players per room, idle-room expiry (10 min), hard room age cap (6 h), bounded rate-limiter state (LRU eviction), no unbounded per-player data. |
| Spoofed client IP (to dodge limits) | `X-Forwarded-For` is read from the **right** by the configured number of trusted hops only. Uvicorn proxy-header rewriting is disabled. |
| Host-header attacks / DNS rebinding | `HostGuard` middleware rejects unknown `Host` values (health check path exempted). |
| XSS | React escapes everything; no `dangerouslySetInnerHTML`; names are NFKC-normalised and restricted to letters, numbers, a few punctuation marks and emoji (control, format and bidi characters rejected); CSP `default-src 'none'`, `script-src 'self'`, no `unsafe-inline`, no `unsafe-eval`. |
| Clickjacking / sniffing / leakage | `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, COOP/CORP same-origin, restrictive `Permissions-Policy`, HSTS (2 years, production only). |
| Injection | No string-built SQL (SQLAlchemy bound parameters); every client message is validated against strict shapes and ranges (`as_int` rejects bools, floats, strings); pydantic models forbid extra fields. |
| Information disclosure | Generic error bodies; validation errors never echo input; `/docs` and `/openapi.json` disabled in production; server banner removed; logs contain no names, tokens or room codes; access log off. |
| Cheating by reading other players' state | Server-authoritative engine. `view_for(player)` is the only place views are built. Tests assert the killer, fake slots, sealed price modifier and others' rankings never reach other players before reveal. |
| TV mode (read-only big screen) | Same trust as joining: needs the room code, issued via `POST /api/rooms/<code>/tv` on the join rate-limit bucket with the same wrong-code penalty. Token in the first WS frame, never the URL. Max 2 screens per room (oldest evicted and its token stops working). Read-only server-side, never a contestant, doesn't keep an idle room alive, and only ever gets the spectator view (tests assert no cards, guesses, rankings or killer). |
| Host tools | Kick, lock and rename are host-only and validated server-side. Kick only between games; the seat (and its token) is removed and the socket closed with app code 4001. A locked room refuses new players. Titles are cleaned like names. |
| Hidden roles in new games | Mole in the Mural: the painting is in no view for the Mole or a TV until the end, hints are revealed per round, and the Mole's hints are never validated (a refusal would reveal the painting). Telepathy Tax: picks only after the reveal. Price: sabotage/double-or-nothing only in their owner's view. All covered by `view_for` tests and the simulator. |
| Chat | Plain text only, 1-200 characters, whitespace collapsed, control and invisible formatting characters rejected (the emoji zero-width joiner is allowed); rendered by React as text. Rate-limited per person (one message per 0.9 s) and per room (12 per 5 s). Only the last 80 messages are kept, in memory and in the room's snapshot, and they go when the room does; chat text is never logged. Team messages are built into each viewer's state only for that team's current members (tests assert the other team never receives them), team talk is cleared when a new game starts, and games can forbid chat where it would be cheating (Codewords Spymasters are muted mid-game; Last Card partners get no private channel). The TV can read but never post. |
| Voice and video calls (LiveKit) | Off unless `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` are set. Media goes through LiveKit, never our server, which only signs short-lived join passes (HS256, 2 h) over the already authenticated WebSocket, for room members only, rate-limited (one per 5 s each). The LiveKit room name is an HMAC of the room code (LiveKit never sees the code); identity is the random seat id. TV passes can't publish, and no pass can send data (game state never travels through the call). Removing someone from the room also removes them from the call. The camera starts off. When calls are on, and only then, the CSP `connect-src` adds the configured LiveKit host (and `*.livekit.cloud` for LiveKit Cloud's regional hosts) and `Permissions-Policy` allows camera and microphone for this site only. This is the one deliberate exception to "no third-party requests". The LiveKit client library is bundled (no CDN) and only downloaded when someone joins a call. |
| Rigged chaos spin (Price Is Weird) | The modifier is committed (`sha256(modifier:nonce)`) before guesses and the nonce is revealed afterwards. |
| Supply chain | Dependabot, `pip-audit`, `npm audit`, Trivy image scan, gitleaks, CodeQL, non-root container, lockfiles (see TODO in kickoff prompt to add hashes). |
| Secrets in the repo | `.env*` ignored, `SECRET_KEY` generated by Render (`generateValue`), production refuses to boot with a short or missing key. |

## What is stored

- **In memory, per room:** display names, scores, game state. Deleted when the room expires.
- **Room snapshots (Postgres, `room_snapshots`):** the same room state, saved after every change so a
  restart or deploy doesn't end a game. Deleted when the room expires (and purged at startup if older
  than a room can live). Snapshots are pickles, so each is HMAC-signed with `SECRET_KEY` and never
  unpickled unless the signature checks out: a row written by anyone else is ignored.
- **In Postgres (optional):** anonymous per-game summaries (`game_id`, timestamp, player count, a score
  aggregate). No names, IPs, tokens or room codes. The app runs fine if the database is unavailable.
- **Accounts (optional, `users` / `sessions` / `results`):** a username, an scrypt password hash, an
  HMAC of the recovery code, coins and owned power-ups; the SHA-256 of each session token (never the
  token); and one row per finished game (game, place, points, coins, month). No email, no IP. Deleting
  the account deletes all of it. Room seats remember their account id in memory and in the snapshot,
  never in any view sent to a client.

## Accounts

- Passwords: `hashlib.scrypt` (n=2^14, r=8, p=1, 16-byte salt), 8-128 characters, a small common-password
  list; hashing runs in a thread so it can't stall live games.
- Sessions: 256-bit random token in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` in production),
  30 days; stored hashed; logout deletes it; a password change or recovery deletes every session.
- Cross-site writes: every state-changing account call needs an allowed `Origin` (required in production)
  on top of `SameSite=Strict` and JSON-only bodies.
- Guessing: `/api/auth/*` has its own per-IP bucket (10/min), plus a per-username lockout after 5 failures
  that doubles each time (max an hour). Unknown usernames get the same error after the same scrypt work.
- Recovery without email: a one-time 20-character code shown once at sign-up; using it issues a new one.
- Coins can't be minted by clients: they're paid by the server from game results (one row per account per
  game, 600 a day cap); buying is a single locked transaction; a power-up is spent before it's played and
  refunded if it can't land.

## Known limitations (be aware, decide, document)

1. **Single instance.** Room state is in process memory (snapshotted to Postgres), so the service runs
   one uvicorn worker. A restart or deploy resumes live rooms from their snapshots; during the few
   seconds a deploy runs old and new servers side by side, the last save wins. To scale horizontally,
   move room state and pub/sub to Redis (Render Key Value) behind the `Hub` seam.
2. **In-memory rate limits** reset on restart and are per instance.
3. **Anonymous play** means a determined user can create many identities from many IPs. Cloudflare
   Turnstile on room creation is the recommended next step if abuse appears.
4. **No account recovery** by design: lose your tab storage and you lose your seat (rooms are short-lived).
5. `style-src 'self'` relies on React setting styles through the DOM API (allowed under CSP), not inline `<style>` tags. Do not add inline `<style>` or `style=""` in static HTML.

## Client IP and Cloudflare

Rate limits are per client IP, so the app must find the real one and nothing a client can forge.

**On Render (verified live, 2026-10-03):** Render's edge is Cloudflare. `X-Forwarded-For` arrives as
`<anything the client sent>, <client>, <Cloudflare edge>`. With `TRUSTED_PROXY_HOPS=1` the app keyed
limits on the Cloudflare edge address: shared by unrelated players and changing between requests, so a
burst with a forged header was never limited. render.yaml therefore sets
`CLIENT_IP_HEADER=cf-connecting-ip`. Cloudflare overwrites that header on every request, and when it is
set the app ignores `X-Forwarded-For` entirely (missing or malformed falls back to the TCP peer).

**Adding your own Cloudflare zone in front (custom domain):**

1. Add the domain to Cloudflare and create a **Proxied** CNAME to `<service>.onrender.com`. Add the
   same hostname under Render → Settings → Custom Domains and wait for it to verify.
2. SSL/TLS: **Full (strict)**, **Always Use HTTPS** on. Network: **WebSockets** on (the default).
3. Render → Environment: `ALLOWED_HOSTS=<your hostname>`, `ALLOWED_ORIGINS=https://<your hostname>`.
   Keep `CLIENT_IP_HEADER=cf-connecting-ip`; Cloudflare keeps the original visitor in it when one
   Cloudflare zone proxies to another.
4. Optional, to force all traffic through your zone's WAF and bot rules: generate a secret
   (`python -c "import secrets;print(secrets.token_urlsafe(48))"`), add a Transform Rule → Modify
   Request Header → Set static `X-Edge-Auth` to it, and set `EDGE_SECRET` to the same value on Render.
   Requests without it then get 403 (WebSocket close 1008); `/healthz` stays open.
5. Optional: Bot Fight Mode, and a WAF rate-limiting rule on `/api/rooms`.
6. Verify (and record the output in docs/SECURITY-EVIDENCE.md): a burst of `POST /api/rooms` with a
   different forged `X-Forwarded-For` **and** `CF-Connecting-IP` on every request still gets 429 after
   about 5; `curl -I` shows the security headers on your hostname.

Steps 1-5 are not yet run against a real custom domain.

`TRUSTED_PROXY_HOPS` is only for hosts without such a header: set it to exactly the number of proxies
that append to `X-Forwarded-For`. Production refuses `TRUSTED_PROXY_HOPS>=2` unless `EDGE_SECRET` or
`CLIENT_IP_HEADER` is set.

## Reporting a vulnerability

Open a private GitHub security advisory ("Report a vulnerability" on the repo's Security tab).

## Launch checklist

- [ ] `SECRET_KEY` set by Render, never committed
- [ ] `ENV=production`, `/docs` returns 404
- [ ] `curl -I https://<host>/` shows CSP, HSTS, `nosniff`, `frame-ancestors 'none'`
- [ ] WebSocket from a foreign origin is refused (see `tests/test_api.py::test_ws_origin_enforced_in_production`)
- [ ] CI green: ruff, bandit, pip-audit, pytest, npm audit, Trivy, gitleaks, CodeQL
- [ ] Client IP is right: a create burst with forged `X-Forwarded-For` / `CF-Connecting-IP` still
      gets 429 (on Render: `CLIENT_IP_HEADER=cf-connecting-ip`)
- [ ] Load test one room with 8 sockets, plus a flood from one IP, and confirm 429/1008 behaviour
