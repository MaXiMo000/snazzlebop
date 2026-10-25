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
  SameSite=Strict session cookies, with an optional authenticator-app second step (TOTP) and
  single-use backup codes.
- **Account email.** Optional. Emailed links are random, stored only as hashes, single use and
  short-lived, and carried in the link's fragment so they never reach server logs. A forgotten-password
  request answers the same whether or not the account exists. Notices about password, sign-in and
  security changes go only to a confirmed address. Logs never contain addresses or links.
- **Sign in with Google.** Server-side OpenID Connect with PKCE, a nonce and a signed, short-lived state
  cookie; the ID token is verified against Google's keys (signature, issuer, audience, expiry). Accounts
  are matched by Google's account id only, never by email, so a Google account can't take over an
  existing one. An authenticator app, when on, is still asked for after Google. Accounts without a
  password confirm sensitive changes with a recent sign-in.
- **Notifications and presence.** Push payloads are encrypted to each browser (RFC 8291) and hold
  only a short text and a link on this site. The server only ever sends to the browsers' own push
  services (an allowlist, https only), so a forged subscription can't make it call anywhere else.
  Presence is visible only to friends and clubmates, and anyone can appear offline. Inbox entries
  and limits are per account; invites only reach friends who added you back, or clubmates.
- **Blocking and reports.** Blocks are silent and apply everywhere: friends, invites, presence,
  joining rooms and room chat. Report context is captured by the server, not supplied by the reporter.
  Moderators act only on roles below their own, and every action is recorded in an audit log.
- **Staff access.** The staff console exists only for usernames listed in a server secret, and only
  while that account's authenticator app is on; to anyone else it answers "not found". Suspensions end
  every session at once, and a suspended account learns of it only after entering the right password.
- **Places.** A college or work address is used only to send a one-time code (15 minutes, 5 tries)
  and is never stored; a keyed hash makes one address verify one account per place.
- **Integrations.** Report events leave only through an operator-configured webhook, signed with
  HMAC-SHA256 and a timestamp, and carry pseudonymous ids instead of accounts or emails. The
  integration API is off unless a 32+ character token is set and compares it in constant time; it
  can change a case's workflow fields but never act against a person.
- **Private clubs.** A club is visible only to its members. Invite links are random, stored only as
  keyed hashes, expire and run out; roles can act only on roles below their own, and bans stick.
- **Abuse limits.** Rate limits per client on the API, room joins, sign-in and WebSocket messages, caps
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
