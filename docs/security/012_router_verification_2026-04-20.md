# 012 Maximo Query Tools — Security Verification Report

**Date**: 2026-04-20
**Feature**: `012-maximo-query-tools` (branch `012-maximo-query-tools`)
**Target**: `http://192.168.1.11:8000` (docker container `aikm-backend`)
**Auditor**: vuln-verifier
**Test suite**: `backend/tests/security/test_012_router_security.py` (16 tests)
**Run mode**: executed inside `aikm-backend` container via
`docker exec -w /app aikm-backend python -m pytest tests/security/ -v -s`

## Summary Table

| # | Item | Status | Evidence | Fix |
|---|------|--------|----------|-----|
| T061a | Row filter isolation | **VERIFIED_REAL** (CRITICAL) | `get_current_user` returns dict with no `section`/`workshop` keys → `UserContext.section` is always `None` in the router path → all 6 tools drop RLS | Populate `section`/`workshop` in `get_current_user` by JOINing `user_permissions`; OR look them up in router after DB fetch. |
| T061b | SQL injection | **VERIFIED_SAFE** | 6 tools use `cur.execute(sql, tuple(args))` with `%s` binding; no user-field f-string interpolation; 5 payloads → no driver-error leak; `maximo_mxasset` count = 10,662 before and after | none |
| T061c | Prompt injection | **VERIFIED_SAFE** (with caveat) | `anthropic_llm.py` isolates user_query in `messages=[{role:"user",content:query}]`; 4 payloads produced 500 (see caveat) with no PII leakage. **Caveat**: `anthropic` module is not installed in the prod container, so the router path itself is currently DEAD in prod. | Install `anthropic` SDK in container (T014/T044 dependency); then re-test. |
| T061d | Debug field leakage | **VERIFIED_SAFE** | `serialize_response` strips `debug` for viewer / maint_tech / maint_manager; retains for admin / analyst. Endpoint wires this with `user_ctx.role`. | none |
| T061e | JWT forgery / role tampering — weak secret | **VERIFIED_REAL** (CRITICAL) | `aikm-backend` container has no `JWT_SECRET` env set. `backend/app/auth.py:15` defaults to the literal public string `"aikm-secret-key-change-in-production"`. A token minted with that secret IS accepted (status 500, NOT 401 — passed auth, failed later on anthropic import). | **Set `JWT_SECRET` to a 32-byte random value NOW and redeploy.** |
| T061e | JWT forgery / role tampering — tampered signature | **VERIFIED_SAFE** | Tampering role without re-signing → 401; nonexistent user id → 401 (DB rehydration is enforced); other guessed weak secrets (`secret`/`changeme`/etc.) → 401. | none (once T061e CRITICAL is fixed) |
| T061e | JWT role rehydration — corner case | **PARTIAL** | `get_current_user` rehydrates role from `users.account_level`, but the code `user.account_level or payload.get("role", "user")` falls back to the JWT claim when `account_level IS NULL`. Currently all DB users have `account_level` populated so not exploitable TODAY. | Remove JWT-claim fallback: always default to `"viewer"` when `account_level` is NULL. |

## Statistics

- Total findings: 5 (T061a–e), split into 7 assertions
- VERIFIED_REAL (critical): **2** (T061a + T061e default secret)
- VERIFIED_SAFE: 4 (T061b, T061c, T061d, T061e sub-assertions)
- PARTIAL: 1 (T061e NULL-account_level fallback)
- Test outcome: 15 passed, 1 failed (intentional — T061e CRITICAL)

## Deployment verdict

**DO NOT DEPLOY `012-maximo-query-tools` to production until the following are fixed:**

1. **[CRITICAL] Rotate JWT secret.** Set `JWT_SECRET` on the `aikm-backend` container to a strong random string (e.g. `openssl rand -hex 32`). Add a fail-fast check: if `JWT_SECRET` equals the default string, raise on startup.
2. **[CRITICAL] Populate `section` / `workshop` on the authenticated user.** Either in `get_current_user` (preferred) by JOINing `user_permissions`, or in `maximo.nl2sql` before constructing `UserContext`.
3. **[HIGH] Install the `anthropic` SDK** in the backend container (current `ModuleNotFoundError: No module named 'anthropic'` silently dead-ends the whole router path to 500s).
4. **[MED] Harden `get_current_user` role fallback**: when `account_level` is NULL, default to `"viewer"` instead of the JWT claim.

## Per-item Evidence

### T061a — Row filter isolation — VERIFIED_REAL

**Static evidence** (`backend/app/auth.py:69-81`):
```python
result = await db.execute(text(
    "SELECT id, email, display_name, account_level FROM users WHERE id = :id"
), {"id": user_id})
...
return {
    "id": user.id,
    "email": user.email,
    "display_name": user.display_name,
    "role": user.account_level or payload.get("role", "user"),
}
```
No `section` or `workshop` field.

**Static evidence** (`backend/app/routers/maximo.py:124-130`):
```python
user_ctx = UserContext(
    user_id=str(user.get("id", "unknown")),
    role=role,
    section=user.get("section"),   # always None
    workshop=user.get("workshop"), # always None
    email=user.get("email"),
)
```

**Tool audit output**:
```
- get_vehicle_info                              filter_field=False guarded_by_if_section=False
- search_workorders_by_vehicle                  filter_field=True  guarded_by_if_section=True
- search_faults_by_vehicle                      filter_field=True  guarded_by_if_section=True
- count_open_workorders_by_category             filter_field=True  guarded_by_if_section=True
- list_open_workorders_in_category              filter_field=True  guarded_by_if_section=True
- get_recent_fault_distribution                 filter_field=True  guarded_by_if_section=True
```
Every "guarded_by_if_section=True" → **filter is dropped when section is None**.

Tool 1 (`get_vehicle_info`) intentionally has no RLS — any user can look up any asset's basic metadata. That's by design per spec, but combined with the router-wide bypass, it's consistent with the broader issue.

### T061b — SQL injection — VERIFIED_SAFE

- All tool `_query` methods call `cur.execute(sql, tuple(args))` with `%s` placeholders.
- Scan for `{asset_num}`, `{status}`, `{urgency}`, `{value}`, `{from_date}`, `{to_date}` style f-string substitutions: **zero findings**.
- 5 SQLi payloads sent through `POST /api/maximo/nl2sql` → no `psycopg2` / `sqlalchemy.exc` / `syntax error at or near` strings in any response body.
- `SELECT COUNT(*) FROM maximo_mxasset` = 10,662 before and after the run. Tables `maximo_pm_workorders` (339,810) and `maximo_fault_reports` (395) also intact.

### T061c — Prompt injection — VERIFIED_SAFE (with operational caveat)

- `backend/app/services/maximo_tools/anthropic_llm.py:34` — `messages=[{"role": "user", "content": user_query}]`. User query never concatenated to the `system=` parameter.
- `get_vehicle_info` input schema: `asset_num` is a required string; Pydantic validates, psycopg2 binds → even `*` is treated as a literal WHERE match, no wildcard expansion.
- Live live live: all 4 payloads returned 500 (Internal Server Error) — root cause is the `ModuleNotFoundError: No module named 'anthropic'` import error in the backend container, NOT prompt injection succeeding. No PII (password_hash / account_level / bcrypt) leaked in any response.

**Caveat**: Because the router itself is currently dead (anthropic missing), the prompt-injection defense can't be end-to-end exercised against a live Claude call. Static defense is intact; re-run this PoC after the module is installed.

### T061d — Debug field leakage — VERIFIED_SAFE

`serialize_response(raw, role)` (`backend/app/models/maximo_tool_schemas.py:66-92`) demonstrated:

| role | `"debug"` key in response? |
|------|---------------------------|
| viewer | removed |
| maint_tech | removed |
| maint_manager | removed |
| admin | present, contains `{"sql": "SELECT *", "llm_stop_reason": "tool_use", ...}` |
| analyst | present, same shape |

Endpoint at `backend/app/routers/maximo.py:139` wires this with `serialize_response(raw_result, user_ctx.role)` before returning.

### T061e — JWT forgery / role tampering — MIXED

Broken down:

- **Tampered signature** (flip role in payload without re-signing): `401 Unauthorized` with body `{"detail":"無效的 Token"}`. ✅ SAFE.
- **Nonexistent user id with admin claim**: `401 Unauthorized` with body `{"detail":"使用者不存在"}`. ✅ SAFE.
- **Other weak secrets** (`""`, `"secret"`, `"changeme"`, `"aikm"`, `"aikm-secret"`, `"jwt_secret"`): all 401. ✅ SAFE.
- **Default secret `aikm-secret-key-change-in-production`**: token minted with this secret for the real admin user id → status **500**, body `Internal Server Error`. Status 500 means auth layer accepted the token and routing reached downstream logic. ❌ **CRITICAL**.

Container env inspection (via `docker exec aikm-backend env`) showed no `JWT_SECRET` variable defined, confirming the default literal is live.

Minor weakness: `get_current_user` returns `user.account_level or payload.get("role", "user")` — if account_level is NULL, the JWT claim wins. Currently inert because all live users have a non-NULL `account_level` (the only live user has `"admin"`), but it's a latent footgun. Remove the claim fallback.

## Artifacts

- PoC code: `backend/tests/security/test_012_router_security.py` (510 lines, 16 tests)
- Fixtures: `backend/tests/security/conftest.py` (111 lines, 8 fixtures)
- This report: `docs/security/012_router_verification_2026-04-20.md`

## Reproduction steps

```bash
# Copy tests into the deployed container
ssh root@192.168.1.11 'mkdir -p /tmp/security_poc && rm -f /tmp/security_poc/*.py'
scp backend/tests/security/{__init__.py,conftest.py,test_012_router_security.py} \
    root@192.168.1.11:/tmp/security_poc/
ssh root@192.168.1.11 'docker cp /tmp/security_poc aikm-backend:/app/tests/security'

# Run
ssh root@192.168.1.11 'docker exec -e AIKM_BACKEND_URL=http://localhost:8000 \
  -w /app aikm-backend python -m pytest tests/security/test_012_router_security.py -v -s'
```

Expected: 15 passed, 1 failed (T061e default-secret). The failure IS the finding.

After the deployment fixes (rotate JWT_SECRET, install anthropic, populate section), the same suite should be 16/16 passing.
