#!/bin/bash
# ============================================================
# AI-KM Platform — E2E Test Suite
# Usage: ./backend/scripts/e2e_test.sh [base_url]
# Default: http://192.168.1.11
# ============================================================

set -euo pipefail

BASE_URL="${1:-http://192.168.1.11}"
API="$BASE_URL:8000"
WEB="$BASE_URL:3000"
ADMIN_EMAIL="admin@example.com"
ADMIN_PASS="admin123"

PASS=0
FAIL=0
ERRORS=()

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

# Test helper
assert() {
  local name="$1"
  local result="$2"
  local expected="$3"

  if echo "$result" | grep -q "$expected"; then
    echo -e "  ${GREEN}✅${NC} $name"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}❌${NC} $name"
    echo -e "     Expected: ${expected}"
    echo -e "     Got: ${result:0:200}"
    FAIL=$((FAIL + 1))
    ERRORS+=("$name")
  fi
}

assert_status() {
  local name="$1"
  local status="$2"
  local expected="$3"

  if [ "$status" = "$expected" ]; then
    echo -e "  ${GREEN}✅${NC} $name (HTTP $status)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}❌${NC} $name (HTTP $status, expected $expected)"
    FAIL=$((FAIL + 1))
    ERRORS+=("$name")
  fi
}

echo "======================================================"
echo "  AI-KM Platform E2E Test Suite"
echo "  Target: $API / $WEB"
echo "  $(date)"
echo "======================================================"

# ── 1. Health Check ──────────────────────────────────────────
echo ""
echo -e "${YELLOW}[1/7] Health Check${NC}"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API/health")
assert_status "Backend /health" "$STATUS" "200"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$WEB")
assert_status "Frontend loads" "$STATUS" "200"

# ── 2. Authentication ────────────────────────────────────────
echo ""
echo -e "${YELLOW}[2/7] Authentication${NC}"

# Login
LOGIN_RES=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASS\"}")
assert "Login success" "$LOGIN_RES" '"success":true'

TOKEN=$(echo "$LOGIN_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
if [ -z "$TOKEN" ]; then
  echo -e "  ${RED}❌ Failed to get token, aborting${NC}"
  exit 1
fi

# /me endpoint
ME_RES=$(curl -s "$API/api/auth/me" -H "Authorization: Bearer $TOKEN")
assert "GET /auth/me returns user" "$ME_RES" '"email"'

# Protected endpoint without token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/maximo/nl2sql" \
  -H "Content-Type: application/json" \
  -d '{"question":"test"}')
assert_status "NL2SQL without token → 401" "$STATUS" "401"

# Wrong password
WRONG_RES=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"wrongpass"}')
assert_status "Login with wrong password → 401" "$WRONG_RES" "401"

# ── 3. NL→SQL Query ──────────────────────────────────────────
echo ""
echo -e "${YELLOW}[3/7] NL→SQL Query${NC}"

# Basic query
SQL_RES=$(curl -s -X POST "$API/api/maximo/nl2sql" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"核簽中的工單有哪些？","mode":"fast"}')
assert "Query '核簽中的工單' succeeds" "$SQL_RES" '"success":true'
assert "Query returns data" "$SQL_RES" '"row_count"'

# Ambiguity detection
AMB_RES=$(curl -s -X POST "$API/api/maximo/nl2sql" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"工單數量","mode":"fast"}')
assert "Ambiguous '工單數量' triggers clarification" "$AMB_RES" '"clarification"'

# COUNT query
CNT_RES=$(curl -s -X POST "$API/api/maximo/nl2sql" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"EMU900 資產有幾筆？","mode":"fast"}')
assert "COUNT query succeeds" "$CNT_RES" '"success":true'

# Chart suggestion
CHART_RES=$(curl -s -X POST "$API/api/maximo/nl2sql" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"maximo_mxsr 故障通報各種 status 各有幾筆？","mode":"fast"}')
assert "Group query has chart_suggestion" "$CHART_RES" '"chart_suggestion"'

# ── 4. Maximo Knowledge ──────────────────────────────────────
echo ""
echo -e "${YELLOW}[4/7] Maximo Knowledge${NC}"

# List
KB_RES=$(curl -s "$API/api/maximo/knowledge" \
  -H "Authorization: Bearer $TOKEN")
assert "GET /knowledge returns rules" "$KB_RES" '"rules"'

# Add rule
ADD_RES=$(curl -s -X POST "$API/api/maximo/knowledge/rule" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"content":"e2e_test_rule","tag":"general"}')
assert "Add rule succeeds" "$ADD_RES" '"content":"e2e_test_rule"'

# Get rule ID and delete
RULE_ID=$(echo "$ADD_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
if [ -n "$RULE_ID" ]; then
  DEL_RES=$(curl -s -X DELETE "$API/api/maximo/knowledge/rule/$RULE_ID" \
    -H "Authorization: Bearer $TOKEN")
  assert "Delete rule succeeds" "$DEL_RES" '"success":true'
fi

# Add rule without token
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/maximo/knowledge/rule" \
  -H "Content-Type: application/json" \
  -d '{"content":"should fail","tag":"general"}')
assert_status "Add rule without token → 403" "$STATUS" "403"

# ── 5. Knowledge Base (Documents) ────────────────────────────
echo ""
echo -e "${YELLOW}[5/7] Knowledge Base${NC}"

DOC_RES=$(curl -s "$API/api/kb/documents" \
  -H "Authorization: Bearer $TOKEN")
assert "GET /kb/documents returns list" "$DOC_RES" '"documents"'

# ── 6. Permissions & Audit ───────────────────────────────────
echo ""
echo -e "${YELLOW}[6/7] Permissions & Audit${NC}"

USERS_RES=$(curl -s "$API/api/auth/users" \
  -H "Authorization: Bearer $TOKEN")
assert "GET /auth/users returns users" "$USERS_RES" '"users"'

GROUPS_RES=$(curl -s "$API/api/auth/groups" \
  -H "Authorization: Bearer $TOKEN")
assert "GET /auth/groups returns groups" "$GROUPS_RES" '"groups"'

AUDIT_RES=$(curl -s "$API/api/maximo/audit" \
  -H "Authorization: Bearer $TOKEN")
assert "GET /maximo/audit returns logs" "$AUDIT_RES" '"logs"'

# ── 7. Chat SSE ──────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[7/7] Chat SSE${NC}"

# Test chat stream (capture first few events)
CHAT_RES=$(curl -s -m 30 -X POST "$API/api/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"核簽中的工單有哪些？","top_k":5,"context":[]}' 2>&1 | head -20)
assert "Chat SSE returns step events" "$CHAT_RES" '"type": "step"'
assert "Chat SSE returns sql_result or content" "$CHAT_RES" '"type": "'

# Related docs endpoint
RELATED_RES=$(curl -s -X POST "$API/api/maximo/related-docs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"description":"齒輪箱漏油","top_k":3}')
assert "Related docs search works" "$RELATED_RES" '"documents"'

# Export endpoint
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$API/api/maximo/export?question=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("EMU900 資產有幾筆"))')" \
  -H "Authorization: Bearer $TOKEN")
assert_status "Excel export returns 200" "$STATUS" "200"

# Feedback endpoint
FB_RES=$(curl -s -X POST "$API/api/maximo/feedback" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"test","sql":"SELECT 1","rating":"up"}')
assert "Feedback endpoint works" "$FB_RES" '"success":true'

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "======================================================"
TOTAL=$((PASS + FAIL))
echo -e "  Total: $TOTAL tests | ${GREEN}$PASS passed${NC} | ${RED}$FAIL failed${NC}"
if [ $FAIL -eq 0 ]; then
  echo -e "  ${GREEN}🎉 All tests passed!${NC}"
else
  echo -e "  ${RED}Failed tests:${NC}"
  for err in "${ERRORS[@]}"; do
    echo -e "    - $err"
  done
fi
echo "======================================================"

exit $FAIL
