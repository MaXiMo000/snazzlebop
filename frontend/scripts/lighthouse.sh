#!/usr/bin/env bash
# Lighthouse gate (mobile + desktop) against a running app container.
#   scripts/lighthouse.sh [container]      default container name: snz (must allow Host: localhost)
set -euo pipefail
cd "$(dirname "$0")/.."
APP=${1:-snz}
OUT=lighthouse
mkdir -p "$OUT"
docker build -q -t snazzlebop-lighthouse scripts/lighthouse >/dev/null
for page in "home|/" "join-gate|/r/ABCDE"; do
  name=${page%%|*}; path=${page#*|}
  for preset in mobile desktop; do
    extra=(); [ "$preset" = desktop ] && extra=(--preset=desktop)
    docker run --rm --network "container:$APP" snazzlebop-lighthouse "http://localhost:10000$path" \
      --only-categories=performance,accessibility,best-practices,seo "${extra[@]}" --output=json > "$OUT/$name-$preset.json"
  done
done
node scripts/lighthouse-gate.mjs "$OUT"
