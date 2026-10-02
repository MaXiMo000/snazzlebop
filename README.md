# Snazzlebop!

The party game show where your friends are the contestants. 3-8 players, one room code, no sign-up.
Put the show on a TV, play from your phones.

**Live:** _not deployed yet_. See [Deploy](#deploy).

![Home page](docs/screenshots/home.png)

| Game | Players | What happens |
| --- | --- | --- |
| **Frenemy Radar** | 3-8 | Everyone secretly ranks everyone (themselves too) on silly traits. The reveal shows your *blind spot*: where your self-image clashes with the room. Ends with a shareable result card. |
| **Alibi** | 4-8 | A killer with a partly fake alibi hides among innocents (one of whom has a hazy memory). Grill each other, watch the board flag contradictions, vote. |
| **Price Is Weird** | 2-8 | Guess what absurd things cost. Closest without going over wins. Sabotage a rival, survive the rigged round, go double or nothing on the last item. |
| **Telepathy Tax** | 3-8 | Score for every mind that matches yours, but if more than half the room picks it, the tax collector takes the lot. |
| **Mole in the Mural** | 4-8 | Everyone knows the secret tile except the Mole. Hint with tiles that share a colour or kind, then unmask the bluffer. |
| **Blackjack Showdown** | 2-8 | The whole room against one dealer. Five hands, 1,000 chips each: hit, stand, double, split. Biggest stack wins. |
| **Crossword Race** | 2-8 | A fresh grid every game. First right answer takes the clue; wrong guesses cost you a beat. |

| Lobby | Blackjack | Crossword |
| --- | --- | --- |
| ![Lobby](docs/screenshots/lobby.png) | ![Blackjack](docs/screenshots/blackjack.png) | ![Crossword](docs/screenshots/crossword.png) |

| Mole in the Mural (390 px) | Alibi (390 px) | TV mode |
| --- | --- | --- |
| ![Mural on a phone](docs/screenshots/mural-mobile.png) | ![Alibi on a phone](docs/screenshots/alibi-mobile.png) | ![TV mode](docs/screenshots/tv.png) |

Also: TV mode (read-only big-screen view), host tools (rename the show, lock the room, remove a player),
reconnect into the same seat, generated sound effects (off by default), reduced-motion support, and a web app manifest
so phones can add it to the home screen (no service worker: the game needs a live connection anyway).

**Content.** Every game deals from a large pool without repeats inside a room until the pool runs out.
With `ANTHROPIC_API_KEY` set, the server also asks Claude for fresh items when a game starts, validates
and de-duplicates them, stores them, and adds them to the pool. Without a key, or when the API is rate
limited or down, games use the built-in pools as normal.

Backend: FastAPI + WebSockets (Python 3.13). Frontend: Vite + React + TypeScript, hand-written CSS.
One Docker service serves both from the same origin.

- Developer guide and architecture rules: [CLAUDE.md](CLAUDE.md)
- Threat model, controls, limits, launch checklist: [SECURITY.md](SECURITY.md)
- What was actually tested and the results: [docs/SECURITY-EVIDENCE.md](docs/SECURITY-EVIDENCE.md)

## Quick start

```bash
# API
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:create_app --factory --reload --port 8000
# UI (new terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Or the production image: `docker build -t snazzlebop .` then run it with `ENV=production`,
`SECRET_KEY`, `ALLOWED_HOSTS` and `ALLOWED_ORIGINS` (see [.env.example](.env.example)).

## Deploy

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → pick the repo. [render.yaml](render.yaml) creates the web service
   (Docker) and a private Postgres. `SECRET_KEY` is generated; host and origin allowlists come from
   `RENDER_EXTERNAL_HOSTNAME`.
3. Optional: in the service's Environment tab set `ANTHROPIC_API_KEY` for fresh content. It's a
   dashboard secret and never goes in git.
4. Walk the launch checklist in [SECURITY.md](SECURITY.md) against the live URL.

The free plan sleeps when idle and drops live rooms; use Starter for real game nights.

### Client IP, Cloudflare and custom domains

Render already sits behind Cloudflare, so render.yaml sets `CLIENT_IP_HEADER=cf-connecting-ip`.
Without it the app rate-limited on a shared Cloudflare edge address that clients could steer with a
forged `X-Forwarded-For`. That was found on the live deploy and fixed (see
[docs/SECURITY-EVIDENCE.md](docs/SECURITY-EVIDENCE.md)). For your own Cloudflare zone and custom
domain, follow "Client IP and Cloudflare" in [SECURITY.md](SECURITY.md).

## What is verified, and what isn't

Run locally on Windows 11 + Docker Desktop against the production image (details and output in
[docs/SECURITY-EVIDENCE.md](docs/SECURITY-EVIDENCE.md)):

- 136 backend tests (engines, `view_for` secrecy per game incl. TV spectators, rate limits, tokens,
  middleware, config rules, content validation), ruff, bandit, pip-audit.
- Simulator: bots play all seven games over real WebSockets, scores are recomputed from the rules, and
  no frame ever carries another player's secret.
- Playwright on 390 px and desktop: 14 tests including axe, keyboard, TV mode, host tools, reconnect.
- Locust abuse suite (rate limits, socket caps, oversize/flood closes, slow reader), OWASP ZAP
  baseline, Lighthouse (home 100 a11y/best practices/SEO), colour contrast for every pair.
- Image: Trivy CRITICAL/HIGH (fixable) clean, gitleaks over full history clean.
- CI on GitHub Actions green (backend, frontend, docker incl. Trivy/simulator/Playwright/Lighthouse/ZAP,
  abuse, gitleaks, CodeQL); every action pinned to a commit SHA, read-only default token.

**Not verified yet:**

- The live Render deployment and the launch checklist against it.
- Cloudflare: the edge steps are written from documented behaviour and the edge-secret check is tested
  locally, but the hop count has not been checked through a real Cloudflare → Render chain.
- Claude content generation against the real API. It's unit-tested with a stubbed client; no key has
  been used yet.

**Limits by design:** one instance with in-memory rooms and rate limits (a restart ends live games),
anonymous play (many IPs can make many players), and no external security review or pen test. This is
a strong, evidenced baseline, not a guarantee.
