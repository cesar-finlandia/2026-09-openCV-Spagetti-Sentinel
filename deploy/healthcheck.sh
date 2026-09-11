#!/bin/bash
# Probe GET <url>/healthz until 200 with the expected build marker (when given).
# Usage: bash deploy/healthcheck.sh [--url <base>] [--marker <expected>] [--retries 20] [--interval 10]
set -euo pipefail

URL="http://localhost:8000"
MARKER=""
RETRIES=20
INTERVAL=10

while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --marker) MARKER="$2"; shift 2 ;;
    --retries) RETRIES="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    *) echo "unknown flag $1" >&2; exit 2 ;;
  esac
done

BODY=""
for _i in $(seq 1 "$RETRIES"); do
  BODY="$(curl -fsS --max-time 8 "$URL/healthz" || true)"
  if [ -n "$BODY" ]; then
    STATUS="$(echo "$BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)"
    if [ "$STATUS" = "ok" ] || [ "$STATUS" = "degraded" ]; then
      if [ -n "$MARKER" ]; then
        DEPLOYED="$(echo "$BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('build_marker',''))" 2>/dev/null || true)"
        if [ "$DEPLOYED" != "$MARKER" ]; then
          echo "healthcheck: marker mismatch — deployed=${DEPLOYED} expected=${MARKER}"
          sleep "$INTERVAL"
          continue
        fi
        echo "healthcheck: ok marker=${MARKER}"
        exit 0
      fi
      echo "healthcheck: ok marker=${DEPLOYED:-unknown}"
      exit 0
    fi
  fi
  sleep "$INTERVAL"
done

echo "healthcheck: FAILED after ${RETRIES} attempts"
echo "healthcheck: url=${URL}/healthz"
echo "healthcheck: last body=${BODY:-<empty>}"
exit 1
