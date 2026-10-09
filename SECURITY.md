# Security policy

## Reporting a vulnerability

Please report security issues privately: open a GitHub security advisory ("Report a vulnerability" on
this repository's **Security** tab). Don't open a public issue. You'll get a reply as soon as possible,
and a fix will be credited to you if you like.

Only the latest version on `main` (the live deployment) is supported.

## How the app protects players

- **Server-authoritative games.** Clients only send intents; each player receives only what they're
  allowed to see, and secrets (hidden roles, sealed answers, other players' hands) never leave the
  server before their reveal.
- **Strict input handling.** Every message is validated against a fixed shape and range; names, chat
  and other text are length-limited and stripped of control and invisible characters. No dynamic SQL,
  no `eval`.
- **Signed, scoped tokens.** Seat tokens are signed, tied to one room and seat, expire, and travel in
  the first WebSocket message, never in a URL. Accounts use scrypt password hashes and HttpOnly,
  SameSite=Strict session cookies.
- **Abuse limits.** Rate limits per client on HTTP, room joins, sign-in and WebSocket messages, caps
  on connections, rooms, players and message size, and idle and age limits for rooms.
- **Browser hardening.** A strict Content Security Policy (same origin only, no inline scripts or
  styles), plus framing, sniffing, referrer and cross-origin isolation headers, and HSTS in
  production. The only third party is the voice/video service when calls are configured: the browser
  may then connect to that host, and camera and microphone are allowed for this site only.
- **Privacy.** Play is anonymous by default. Logs contain no names, tokens, room codes or chat. Rooms,
  their chat and their snapshots are deleted when the room ends. Call media never passes through the
  app's server.
- **Supply chain.** Pinned dependencies and lockfiles, a non-root container, and automated scanning
  (CodeQL, dependency audits, container scanning, secret scanning) in CI.

## Deploying safely

Production refuses to start with a weak or missing `SECRET_KEY` or without host and origin allowlists.
Keep every secret (the secret key, database URL and API keys) in your host's environment settings,
never in the repository. See [.env.example](.env.example) for every setting.
