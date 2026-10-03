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
    # Lighthouse sometimes fails to record a trace (NO_NAVSTART, "please run Lighthouse again"):
    # that's the tool, not the page, so try up to 3 times. Scores are still judged by the gate.
    for attempt in 1 2 3; do
      if docker run --rm --network "container:$APP" snazzlebop-lighthouse "http://localhost:10000$path" \
        --only-categories=performance,accessibility,best-practices,seo "${extra[@]}" --output=json > "$OUT/$name-$preset.json"; then
        break
      fi
      if [ "$attempt" = 3 ]; then
        echo "Lighthouse crashed 3 times on $name ($preset)"
        exit 1
      fi
      echo "Lighthouse failed on $name ($preset), retrying ($attempt/3)"
      sleep 2
    done
  done
done
node scripts/lighthouse-gate.mjs "$OUT"
