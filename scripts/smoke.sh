#!/usr/bin/env bash
# Smoke test (spec E6 Req 4): health -> upload sample.pdf -> ask a question ->
# assert a citation shows up in the streamed answer. Run after every deploy:
#
#   ./scripts/smoke.sh https://docchat-backend-production-e642.up.railway.app
#
# Exits non-zero (with the failing step named) on any check failure.
set -euo pipefail

BASE_URL="${1:-${SMOKE_BASE_URL:-http://localhost:8000}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE_PDF="$SCRIPT_DIR/../sample/sample.pdf"
EMAIL="smoke-test@docchat.local"
PASSWORD="smoke-test-password-123"

_fail() {
  echo "SMOKE FAIL: $1" >&2
  exit 1
}

echo "==> smoke test against $BASE_URL"

# 1. Health -------------------------------------------------------------
echo "==> health"
health_body="$(curl -sS -w '\n%{http_code}' "$BASE_URL/health")"
health_status="$(echo "$health_body" | tail -1)"
health_json="$(echo "$health_body" | sed '$d')"
[ "$health_status" = "200" ] || _fail "GET /health returned $health_status: $health_json"
echo "$health_json" | grep -q '"status":"ok"' || _fail "/health body missing status:ok — $health_json"
echo "    ok: $health_json"

# 2. Auth (register the fixed smoke account, or log in if it already exists) --
echo "==> auth"
register_body="$(curl -sS -w '\n%{http_code}' -X POST "$BASE_URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")"
register_status="$(echo "$register_body" | tail -1)"
register_json="$(echo "$register_body" | sed '$d')"

if [ "$register_status" = "201" ]; then
  auth_json="$register_json"
elif [ "$register_status" = "409" ]; then
  login_body="$(curl -sS -w '\n%{http_code}' -X POST "$BASE_URL/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")"
  login_status="$(echo "$login_body" | tail -1)"
  auth_json="$(echo "$login_body" | sed '$d')"
  [ "$login_status" = "200" ] || _fail "POST /auth/login returned $login_status: $auth_json"
else
  _fail "POST /auth/register returned $register_status: $register_json"
fi

TOKEN="$(echo "$auth_json" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)"
[ -n "$TOKEN" ] || _fail "no access_token in auth response: $auth_json"
echo "    ok: signed in as $EMAIL"

# 3. Upload sample.pdf, wait for the terminal SSE event ------------------
echo "==> upload $SAMPLE_PDF"
[ -f "$SAMPLE_PDF" ] || _fail "sample PDF not found at $SAMPLE_PDF"
upload_stream="$(curl -sS -N -X POST "$BASE_URL/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$SAMPLE_PDF;type=application/pdf")"
echo "$upload_stream" | grep -q '"stage": *"ready"' \
  || _fail "upload never reached stage:ready — $upload_stream"
DOC_ID="$(echo "$upload_stream" | grep -o '"doc_id": *"[^"]*"' | head -1 | cut -d'"' -f4)"
echo "    ok: ingested doc_id=$DOC_ID"

# 4. Ask a question, assert a citation appears in the streamed answer ----
echo "==> chat"
chat_stream="$(curl -sS -N -X POST "$BASE_URL/chat/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is this document about? Cite your sources."}')"

echo "$chat_stream" | grep -q '^event: error' \
  && _fail "chat stream emitted an error event — $chat_stream"
echo "$chat_stream" | grep -q '^event: done' \
  || _fail "chat stream never reached a done event — $chat_stream"
echo "$chat_stream" | grep -q '"cited": *true' \
  || _fail "no cited source in the sources event — $chat_stream"

echo "    ok: streamed answer includes a cited source"

# 5. Cleanup: remove the smoke-test document so prod data stays tidy -----
if [ -n "$DOC_ID" ]; then
  curl -sS -o /dev/null -X DELETE "$BASE_URL/documents/$DOC_ID" -H "Authorization: Bearer $TOKEN" || true
fi

echo "==> SMOKE PASS"
