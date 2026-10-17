#!/usr/bin/env bash
# Pull images from ECR Public, falling back to a mirror when ECR rate-limits the (shared) CI runner
# IP. Base images pulled from a mirror are re-tagged with their ECR name, so `docker build` uses the
# local copy. Prints the usable reference for each argument, one per line (digest pins can't be
# re-tagged, so callers run whatever reference comes back).
set -euo pipefail

pull() {
  for wait in 5 15 0; do
    docker pull -q "$1" >/dev/null 2>&1 && return 0
    sleep "$wait"
  done
  return 1
}

for ref in "$@"; do
  if pull "$ref"; then
    echo "$ref"
    continue
  fi
  case "$ref" in
    public.ecr.aws/docker/library/*) alt="mirror.gcr.io/library/${ref#public.ecr.aws/docker/library/}" ;;
    public.ecr.aws/aquasecurity/*) alt="ghcr.io/aquasecurity/${ref#public.ecr.aws/aquasecurity/}" ;;
    *) echo "no mirror for $ref" >&2; exit 1 ;;
  esac
  echo "ECR refused $ref, using $alt" >&2
  pull "$alt" || { echo "could not pull $ref or $alt" >&2; exit 1; }
  if [[ $ref == *@* ]]; then
    echo "$alt"
  else
    docker tag "$alt" "$ref"
    echo "$ref"
  fi
done
