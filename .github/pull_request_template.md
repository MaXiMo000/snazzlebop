## What changes

<!-- One or two sentences. Screenshots (phone and laptop) for anything visible. -->

## Checklist

- [ ] Tests for the new behaviour (and a failing test first for a bug fix)
- [ ] Changed a model in `app/db.py`? A migration in `app/migrations/versions/`, reviewed, with a working downgrade
- [ ] Changed a route or `app/schemas.py`? `python scripts/export_openapi.py` and `npm run gen:api` run, files committed
- [ ] Changed a game? Secrecy tests for players, the TV and the audience still pass; `scripts/simulate.py --only <game>` passes
- [ ] Anything a player sees: works at 320 px, on a laptop and on the TV; 44 px targets; keyboard and screen reader
- [ ] No secrets, personal data, internal notes or debug code in the diff
