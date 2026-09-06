#!/usr/bin/env bash
# diagnose_404.sh — Diff SPA-called paths against OpenAPI, then probe each suspect.
#
# Usage:  diagnose_404.sh [admin-password]
#         defaults to "HermesTest2026!" (the standard diagnostic password)
#
# Output:
#   /tmp/spa-paths.txt       — every static /api/* path the SPA requests
#   /tmp/openapi-paths.txt   — every path OpenAPI lists
#   /tmp/suspect-404s.txt    — paths in SPA but not OpenAPI (real or false positive)
#   /tmp/probe-results.txt   — final HTTP probe for each suspect (with auth)
#
# Requires: python3, curl, comm

set -euo pipefail

HOST="${HERMES_WEB_UI_HOST:-http://localhost:8648}"
ADMIN_PASS="${1:-HermesTest2026!}"
ASSETS="/root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/client/assets/js"

echo "=== diagnose_404.sh — Hermes Web UI route probe ==="
echo "Host: $HOST"
echo "Admin password: $ADMIN_PASS"
echo

# ---- 1. Extract SPA-called paths ----
echo "[1/4] Scanning SPA bundles for /api/* references..."
if [[ ! -d "$ASSETS" ]]; then
  echo "FATAL: SPA assets dir not found: $ASSETS" >&2
  exit 2
fi
grep -rohE '"/api/[^"]+"|`/api/[^`]+`' "$ASSETS" \
  | sed -E 's/^["`]|["`]$//g' \
  | grep -v '\${' | grep -v ':[a-z]' \
  | sort -u > /tmp/spa-paths.txt
SPA_COUNT=$(wc -l < /tmp/spa-paths.txt)
echo "  → $SPA_COUNT static paths"

# ---- 2. Pull OpenAPI catalog ----
echo "[2/4] Fetching OpenAPI route catalog..."
curl -sS "$HOST/api/openapi.json" \
  | python3 -c "import json,sys;[print(p) for p in json.load(sys.stdin)['paths']]" \
  | sort -u > /tmp/openapi-paths.txt
OAPI_COUNT=$(wc -l < /tmp/openapi-paths.txt)
echo "  → $OAPI_COUNT paths"

# ---- 3. Compute diff ----
echo "[3/4] Diffing SPA calls vs OpenAPI..."
comm -23 /tmp/spa-paths.txt /tmp/openapi-paths.txt > /tmp/suspect-404s.txt
SUSPECT_COUNT=$(wc -l < /tmp/suspect-404s.txt)
echo "  → $SUSPECT_COUNT suspects"

if [[ "$SUSPECT_COUNT" -eq 0 ]]; then
  echo "  (no suspects — every SPA path is in OpenAPI)"
  echo "  If user still reports 404, check wrong method or wrong token, not missing route."
  exit 0
fi

# ---- 4. Login and probe each suspect ----
echo "[4/4] Logging in and probing each suspect with GET and POST..."
TOKEN=$(curl -sS -X POST "$HOST/api/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-For: 10.10.10.10" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASS\"}" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('token',''))")

if [[ -z "$TOKEN" ]]; then
  echo "FATAL: login failed. Check admin password." >&2
  exit 3
fi

: > /tmp/probe-results.txt
while IFS= read -r url; do
  for method in GET POST; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X "$method" \
      "$HOST$url" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -H "X-Forwarded-For: 10.10.10.10" \
      -d '{}')
    printf "  %-5s %-55s → %s\n" "$method" "$url" "$code" | tee -a /tmp/probe-results.txt
  done
done < /tmp/suspect-404s.txt

echo
echo "=== Summary ==="
REAL_404S=$(awk '$3==404 {print $2}' /tmp/probe-results.txt | sort -u)
if [[ -n "$REAL_404S" ]]; then
  echo "❌ Genuine 404 (real bugs):"
  echo "$REAL_404S" | sed 's/^/    /'
else
  echo "✅ No genuine 404. Every SPA-called path exists on the backend."
  echo "   Likely cause of user's '404' report: wrong method, expired token,"
  echo "   or SPA fallback eating the request."
fi

echo
echo "Files:"
echo "  /tmp/spa-paths.txt"
echo "  /tmp/openapi-paths.txt"
echo "  /tmp/suspect-404s.txt"
echo "  /tmp/probe-results.txt"