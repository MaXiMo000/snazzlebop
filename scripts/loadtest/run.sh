#!/usr/bin/env bash
# Build the app and the abuse suite, run both on a private network, print the verdicts.
#   scripts/loadtest/run.sh              -> exit 0 only if every scenario passed
set -euo pipefail
cd "$(dirname "$0")/../.."
NET=snz-abuse
APP=snz-abuse-app
cleanup() { docker rm -f "$APP" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
docker network create "$NET" >/dev/null
docker build -q -t snazzlebop . >/dev/null
docker build -q -t snazzlebop-abuse scripts/loadtest >/dev/null
# No proxy in front, so TRUSTED_PROXY_HOPS=0: the suite's container IP is the client IP.
docker run -d --name "$APP" --network "$NET" \
  -e ENV=production -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))' 2>/dev/null || python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e ALLOWED_HOSTS="$APP" -e ALLOWED_ORIGINS="http://$APP:10000" -e TRUSTED_PROXY_HOPS=0 \
  snazzlebop >/dev/null
for _ in $(seq 1 30); do
  docker exec "$APP" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:10000/healthz',timeout=1)" 2>/dev/null && break
  sleep 1
done
status=0
docker run --rm --network "$NET" -e ABUSE_ONLY="${ABUSE_ONLY:-}" snazzlebop-abuse --host "http://$APP:10000" || status=$?
echo "--- app log (should contain no room codes, names or tokens) ---"
docker logs "$APP" 2>&1 | tail -20
exit $status
