"""Module boundaries, checked on every build so the structure holds as the team grows.

- Game engines are pure: only the standard library and other games (no web, database or room code).
- The rule modules (coins, show, schemas, ...) stay pure too, so they can be tested without I/O.
- The room hub knows nothing about HTTP or the database: it talks through small protocols.
- Web frameworks live only at the edges (main, accounts, ws); SQL only in db.
- Nothing imports app.main (the composition root).
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
STDLIB = set(sys.stdlib_module_names) | {"__future__"}

# area -> (app areas it may import, third-party packages it may import)
RULES: dict[str, tuple[set[str], set[str]]] = {
    "app.games": ({"app.games"}, set()),
    "app.coins": (set(), set()),
    "app.prank": (set(), set()),
    "app.security": (set(), set()),
    "app.config": (set(), set()),
    "app.logging_setup": (set(), set()),
    "app.show": ({"app.games"}, set()),
    "app.schemas": (set(), {"pydantic"}),
    "app.mfa": (set(), {"segno"}),  # pure: the time is passed in; segno only draws the QR code
    "app.emails": (set(), set()),  # pure: a description in, HTML and text out
    "app.mailer": ({"app.config", "app.emails"}, set()),  # stdlib only: Resend over HTTPS, or SMTP
    "app.presence": (set(), set()),  # pure: who's around and "up for a game", clock injected
    "app.webpush": (set(), {"cryptography"}),  # push encryption and VAPID only
    "app.oidc": (set(), {"cryptography"}),  # Google sign-in protocol: state, PKCE, ID token checks
    "app.ratings": (set(), set()),  # the rating model, seasons and tiers
    "app.battles": (set(), set()),  # battle prizes and limits
    "app.fairplay": (set(), set()),  # anti-farming rules for every payout
    "app.progress": (set(), set()),  # levels and daily quests
    "app.party": (set(), set()),  # party items: room effects with no effect on scores
    "app.notify": ({"app.config", "app.webpush"}, set()),  # rules and fan-out; storage passed in
    "app.events": (set(), set()),  # pure: the versioned shape of events other systems receive
    "app.outbox": ({"app.config", "app.events"}, set()),  # delivery with retries; storage passed in
    "app.calls": ({"app.config"}, set()),
    "app.billing": ({"app.config"}, set()),  # Plus and ads rules, Paddle signatures (stdlib only)
    "app.persist": ({"app.rooms"}, set()),
    "app.rooms": (
        {"app.rooms", "app.games", "app.config", "app.security", "app.calls", "app.persist", "app.prank"}
        | {"app.coins", "app.show", "app.ratings", "app.battles", "app.fairplay", "app.party"},
        set(),
    ),
    "app.contentgen": ({"app.games"}, {"anthropic"}),
    "app.db": (
        {"app.ratings", "app.battles", "app.fairplay", "app.progress", "app.games", "app.billing"},
        {"alembic", "sqlalchemy"},
    ),  # storage; uses the pure rules
}
EDGES = {
    "app.main",
    "app.accounts",
    "app.clubs",
    "app.notifications",
    "app.safety",
    "app.integrations",
    "app.staff",
    "app.places",
    "app.ranked",
    "app.quests",
    "app.plus",
    "app.ws",
    "app.migrations",
}  # may use the frameworks


def imports(path: Path, module: str) -> set[str]:
    """Top-level packages, and app areas (app.<name>), imported by one file."""
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                parts = [*base, *(node.module.split(".") if node.module else [])]
                if not node.module:  # "from . import calls": each name is a module
                    out |= {".".join([*parts, a.name][:2]) for a in node.names}
                    continue
            else:
                parts = (node.module or "").split(".")
            out.add(".".join(parts[:2]) if parts[0] == "app" else parts[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                out.add(".".join(parts[:2]) if parts[0] == "app" else parts[0])
    return out


def files() -> list[tuple[str, str, Path]]:
    """(area, module, path) for every app source file."""
    out = []
    for path in sorted(APP.rglob("*.py")):
        module = ".".join(path.relative_to(APP.parent).with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        out.append((".".join(module.split(".")[:2]), module, path))
    return out


class BoundaryTests(unittest.TestCase):
    def test_every_area_imports_only_what_it_may(self):
        for area, module, path in files():
            if area in EDGES or module == "app":
                continue
            self.assertIn(area, RULES, f"{module}: a new area needs a rule in tests/test_boundaries.py")
            allowed_app, allowed_pkgs = RULES[area]
            for dep in imports(path, module):
                if dep in STDLIB or dep == area:
                    continue
                if dep.startswith("app"):
                    self.assertIn(dep, allowed_app | {area}, f"{module} may not import {dep}")
                else:
                    self.assertIn(dep, allowed_pkgs, f"{module} may not import the package {dep}")

    def test_nothing_imports_the_composition_root(self):
        for _, module, path in files():
            if module != "app.main":
                self.assertNotIn("app.main", imports(path, module), module)

    def test_the_checker_sees_a_violation(self):
        # Guard the guard: a game importing the room hub must be caught.
        src = APP / "games" / "_probe_boundary.py"
        src.write_text("from ..rooms import Hub\nimport fastapi\n", encoding="utf-8")
        try:
            found = imports(src, "app.games._probe_boundary")
        finally:
            src.unlink()
        self.assertIn("app.rooms", found)
        self.assertIn("fastapi", found)
