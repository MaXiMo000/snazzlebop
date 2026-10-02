# Snazzlebop!

Party games for 3-8 friends in the browser: one room code, no signup, comic-book UI.

| Game | Players | What happens |
| --- | --- | --- |
| **Frenemy Radar** | 3-8 | Everyone secretly ranks everyone (themselves too) on silly traits. The reveal shows where your self-image clashes with the room: your *blind spot* score. |
| **Alibi** | 4-8 | A killer with a scripted, partly fake alibi hides among innocents. Share and grill alibis, watch the board flag contradictions, vote. |
| **Price Is Weird** | 2-8 | Guess the price of something absurd. Closest without going over wins, then the sealed chaos spin doubles or halves the real price. |

Backend: FastAPI + WebSockets (Python 3.13). Frontend: Vite + React + TypeScript with hand-written CSS.
One Docker service on Render serves both, same origin.

- Developer guide and architecture rules: [CLAUDE.md](CLAUDE.md)
- Threat model, controls, limits, launch checklist: [SECURITY.md](SECURITY.md)
- Hand-off prompt for Claude Code: [docs/KICKOFF_PROMPT.md](docs/KICKOFF_PROMPT.md)

## Quick start

```bash
# API
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:create_app --factory --reload --port 8000
# UI (new terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

## Deploy

Render → New → Blueprint → select this repo (`render.yaml`). Details in [CLAUDE.md](CLAUDE.md) and
[SECURITY.md](SECURITY.md) ("Edge setup" for Cloudflare + DDoS protection).

## Status of this scaffold

Verified when it was written (no network access to package registries):

- 60 unit tests pass with the standard library only: all three game engines (including secrecy of
  hidden state, input validation, scoring), the room hub, signed tokens, rate limiter, client-IP
  resolution, host/headers/body/rate-limit middleware, and config rules.

**Not yet run** (needs `pip`/`npm`): the FastAPI integration tests (`backend/tests/test_api.py`), the
frontend typecheck and build, the Docker image, and the Render deploy. The kickoff prompt starts by
doing exactly that.
