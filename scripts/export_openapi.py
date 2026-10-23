"""Write the API contract (OpenAPI, plus the WebSocket state frame) to frontend/openapi.json, the source
the apps generate their API types from (frontend: `npm run gen:api`).

    python scripts/export_openapi.py           # rewrite it after changing a route or app/schemas.py
    python scripts/export_openapi.py --check   # CI: fail if the committed copy is out of date
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import TypeAdapter  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schemas import RoomFrame  # noqa: E402

OUT = ROOT / "frontend" / "openapi.json"


def document() -> str:
    doc = create_app(Settings(secret_key="x" * 40)).openapi()
    doc["info"] = {"title": "Snazzlebop API", "version": "1"}
    # The WebSocket "state" frame isn't an HTTP response, so it is added to the shared schemas by hand.
    frame = TypeAdapter(RoomFrame).json_schema(ref_template="#/components/schemas/{model}")
    schemas = doc["components"]["schemas"]
    for name, schema in {**frame.pop("$defs", {}), "RoomFrame": frame}.items():
        if name in schemas and schemas[name] != schema:
            raise SystemExit(f"schema {name} differs between the HTTP and realtime contracts")
        schemas[name] = schema
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    fresh = document()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != fresh:
            print("frontend/openapi.json is out of date: run python scripts/export_openapi.py")
            return 1
        print("openapi.json is up to date")
        return 0
    OUT.write_bytes(fresh.encode("utf-8"))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
