#!/usr/bin/env python3
"""Grow the built-in content pools with Claude, for review and commit.

    ANTHROPIC_API_KEY=... python scripts/grow_pools.py [--batches 20] [--kinds frenemy price ...]

Runs the same generator the server uses (same validation and de-duplication) and appends everything
that passes to backend/app/games/content_extra.json. Review the diff, then commit it: every room then
deals from the bigger pools even when the server has no API key. Costs real money: one API call per
batch (each asks for ~15 items).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.contentgen import EXTRA_FILE, KINDS, ContentGenerator, claude_caller  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=20, help="API calls per kind")
    ap.add_argument("--kinds", nargs="+", default=list(KINDS), choices=list(KINDS))
    args = ap.parse_args()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("Set ANTHROPIC_API_KEY first.", file=sys.stderr)
        return 1
    extra = json.loads(EXTRA_FILE.read_text(encoding="utf-8")) if EXTRA_FILE.exists() else {}
    gen = ContentGenerator(claude_caller(key), calls_per_hour=10_000)
    for kind in args.kinds:
        start = len(KINDS[kind].pool)
        got = 0
        for i in range(args.batches):
            try:
                added = await gen.generate(kind)
            except Exception as exc:  # rate limit, refusal, bad output: report and keep going
                print(f"  {kind} batch {i + 1}: failed ({type(exc).__name__}: {exc})")
                continue
            extra.setdefault(kind, []).extend(added)
            got += len(added)
            print(f"  {kind} batch {i + 1}: +{len(added)}")
        print(f"{kind}: {start} -> {len(KINDS[kind].pool)} (+{got})")
        EXTRA_FILE.write_text(json.dumps(extra, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
