# Critic Round 3 — 013-postgres-viewer — SECURITY (final pre-Phase-5 sweep)

**Reviewer angle**: verify R2 resolutions; hunt for new holes introduced by the fixes (esp. CSP nonce, purger role, REASSIGN OWNED).
**Scope**: spec.md, plan.md, data-model.md, research.md, quickstart.md, contracts/pg-viewer-api.yaml, tasks.md, critic-round-2-security.md. No code yet.
**Date**: 2026-04-20.

## Verdict: **CONDITIONAL_YES → proceed to Phase 5 Day 1 with 2 HIGH fixes in-flight (non-blocking for T-001..T-010 kickoff)**

All 1 Major + 9 Minor from R2 verified. 0 REGRESSED. 2 new HIGH + 3 new MEDIUM + 3 LOW found. None are showstoppers for migration/engine work — but T-031 (CSP) and T-046 (CSP reporter) MUST absorb the HIGH findings before those tasks close.

---

## R2 verification table

| R2 ID | Claim | Verification | Status |
|---|---|---|---|
| **NEW-M1** purger role | `aikm_audit_purger` with DROP-only via ownership; purge cron runs as it | `data-model.md:241-266` creates role with `CONNECTION LIMIT 2`, NO SELECT/INSERT grants, NO CREATE, NO EXECUTE. `data-model.md:383-385, 404` transfers partition ownership. `quickstart.md §10a:394-425` cron uses `PG_AUDIT_PURGER_PASSWORD` + `-U aikm_audit_purger`. `.env.example` block in `quickstart.md:517-529` includes `PG_AUDIT_PURGER_PASSWORD`. Rotation entry at `quickstart.md §9:366-371`. T-043 acceptance at `tasks.md:462` explicit "runs as aikm_audit_purger, NOT aikm". **Blast-radius check**: purger capabilities confined to DROP on partition children it owns (owner can drop). Cannot DROP DATABASE (no superuser). Cannot touch other tables (no grants). Cannot `GRANT ... TO aikm_audit_purger WITH GRANT OPTION` abuse (no grant-option). | ✅ VERIFIED_FIXED |
| **NEW-M2** CSP | Full directive set in plan.md §5a | `plan.md:75-89` verbatim policy: `default-src 'none'; script-src 'self' 'nonce-{...}' 'strict-dynamic'; style-src 'self' 'nonce-{...}'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'; object-src 'none'; upgrade-insecure-requests; report-uri /api/csp-violations;`. No `'unsafe-inline'` / `'unsafe-eval'`. Nonce via `crypto.randomBytes(16).toString('base64')` at `plan.md:92`, enforced at `tasks.md:290`. Next.js nonce wiring documented at `plan.md:91-97`. | ✅ VERIFIED_FIXED |
| **NEW-M3** pg_hba docs | Deferred (accepted) pending ops subnet info | `plan.md:186,196` still flags as "should restrict… subnet"; no concrete pg_hba edit in quickstart. Planner accepted residual. | ⚠️ PARTIAL (accepted) |
| **NEW-M4** per-partition REVOKE | Per-partition REVOKE + REVOKE in `ensure_next_audit_partition()` | `data-model.md:372-373, 388-391` emit `REVOKE UPDATE, DELETE, TRUNCATE … FROM aikm` + `REVOKE SELECT … FROM aikm_viewer` on both seeded partitions AND inside the function. `quickstart.md:489-490` template includes same REVOKEs. | ✅ VERIFIED_FIXED |
| **NEW-M5** Redis-down fail-closed | 503 + Retry-After: 30 | `plan.md §6:99-101` explicit "fails closed: HTTP 503 + Retry-After: 30". `tasks.md T-014.6:158` integration test: kill Redis → HTTP 503, `{"detail":"rate limiter backend unavailable"}`; audit `status='error'`. Prometheus counter `pg_viewer_rate_limiter_redis_down_total`. `plan.md:160` "MUST NOT fall back to no-limit". | ✅ VERIFIED_FIXED |
| **NEW-M6** info_schema col-name leak | Residual accepted + CI guard | `plan.md:178` risk row + `tasks.md T-013:113` CI test. Planner decision documented. | ⚠️ RISK_ACCEPTED (see new R3-M2) |
| **NEW-M7** sanitizer locale | not in resolution table | No evidence that `SET lc_messages='C'` added to T-010. `critic-round-2-security.md:154` explicitly says "NOT set explicitly". | ⚠️ STILL_OPEN (downgraded to LOW since redacted message is static) |
| **NEW-M8** PII regex tightening | Generic hex rule removed; specific patterns | `data-model.md:151-165` lists `Bearer`, `ghp_`, `github_pat_`, `sk-ant-`, `sk-`, + adjacency rule. Generic `'[A-Fa-f0-9]{20,}'` removed. Truncate AFTER redaction (line 169). | ✅ VERIFIED_FIXED |
| **NEW-M9** psycopg identifier lifecycle | T-012 guardrail | `tasks.md:98,102` requires `psycopg.sql.Identifier(name).as_string(conn)` + "Composed MUST NEVER be passed to asyncpg" guardrail test. Lifecycle of `conn` still fuzzy but no longer security-load-bearing. | ✅ VERIFIED_FIXED |
| **NEW-M10** sqlparse nested comments | T-016 test cases | `tasks.md T-016:193` lists `/* /* */ DROP */ SELECT 1` and `/*! DROP */ SELECT 1` as "reject". False-positive behavior documented. | ✅ VERIFIED_FIXED |
| R2-H1 users_public email | email SAFE for admin, UI mask on audit | `data-model.md:111-140` documents the decision, adds `EMAIL_MASK_UI_COLUMNS` + `mask_email_ui()`. | ✅ VERIFIED_FIXED |
| R2-H2 429 on /tables,/schema | in contract | `contracts/pg-viewer-api.yaml:42-43, 65-66` — both endpoints list 429. | ✅ VERIFIED_FIXED |
| R2-N1 REASSIGN OWNED rollback | quickstart idiom | `quickstart.md §8:326-348` uses `REASSIGN OWNED … TO postgres; DROP OWNED …; DROP TABLE … CASCADE; DROP ROLE …`. Correct order. | ✅ VERIFIED_FIXED |

**Stats**: 10/10 M-series + R2-H1/H2/N1 addressed. 8 VERIFIED_FIXED, 1 PARTIAL-accepted (M3), 1 RISK_ACCEPTED (M6), 1 STILL_OPEN minor (M7).

---

## Round 3 — NEW findings (adversarial)

### 🟠 HIGH

#### R3-H1 — T-046 `/api/csp-violations` is NOT in the OpenAPI contract (endpoint spec-drift + no defined rate-limit backend)
- **Location**: `contracts/pg-viewer-api.yaml` has zero `csp` mentions (grep confirmed). `tasks.md T-046:495-509` defines it in plain prose.
- **Why this matters**:
  1. `report-uri` POSTs happen from every admin browser as soon as CSP ships. **Unauthenticated endpoint, always-on, public-internet-reachable** (whatever origin the admin browses from). Contract drift means no Schemathesis fuzz coverage for this surface — exactly the surface that needs it most.
  2. T-046 says "Rate-limited to 60 req/min/IP (reuse existing rate limiter)" — but per R2 M5 resolution, if Redis is down the rate limiter returns 503 fail-closed. If CSP reports themselves are fail-closed on a Redis outage, every admin's browser retries (or gives up), and we lose the one signal that would tell us CSP is breaking. **Conflicting fail-closed posture**: rate-limiter service-level 503 vs. CSP-reporter "store or fail" — acceptance needs to distinguish.
  3. No body-size cap in the OpenAPI (T-046 says "16 KB" in prose but contract doesn't enforce). Some browsers send 100+ KB reports when `effective-directive` is deeply nested.
  4. `ip_address from trusted XFF` (T-046:503) — but `/api/csp-violations` is PUBLIC/unauthenticated and CSP reports can come from the browser at arbitrary egress IPs. The trusted-XFF allowlist model from `plan.md` applies to admin-authenticated audit — does it apply here? Unclear.
- **Fix direction**:
  - Add `/csp-violations` path to `contracts/pg-viewer-api.yaml`: methods POST (204/400/413/429), body schema for both legacy `csp-report` and `application/reports+json` array forms, max body size 16 KB.
  - T-046 acceptance must specify CSP-reporter behavior when Redis is down: degrade-and-log (write WARN, return 204 anyway) rather than 503 — we prefer to lose report fidelity over forcing browsers to retry.
  - Document that `ip_address` on CSP reports is `request.client.host` (no XFF trust) since CSP reports are not proxied through authenticated flows.
  - Add abuse-cap: per-IP body-size + per-IP daily count (cron-purged), not just per-minute.

#### R3-H2 — Next.js error boundaries + 500 pages bypass CSP middleware (nonce mismatch → blank page OR injected nonceless inline)
- **Location**: `tasks.md T-031:283` — middleware matches `/admin/pg-viewer/:path*`. `plan.md §5a:92` — nonce in `middleware.ts`.
- **Attack surface**:
  1. Next.js 15 App Router emits a built-in `error.tsx` / `global-error.tsx` fallback on unhandled exceptions. Those pages are rendered by the Next runtime and may include inline `<script>` tags for hydration recovery. If the middleware generates a fresh nonce per response but the error boundary's HTML was baked without it, hydration will break under strict CSP — admin sees a blank `/admin/pg-viewer` on every server error, with no visible hint why (because CSP blocks the dev-error bubble too). The "temporarily disabled" banner covers feature-flag-off but NOT 500s.
  2. Worse: common Next.js patterns emit `<script id="__NEXT_DATA__">JSON-blob</script>` with `type="application/json"` — this is safe content-wise, but must still carry the nonce under `script-src 'self' 'nonce-...'`. T-031 acceptance (line 291) asserts `document.querySelectorAll('script:not([nonce])')` is empty — good — BUT this is an integration test against success path only. Error paths untested.
  3. `strict-dynamic` + nonce interaction: if the admin UI anywhere uses `dangerouslySetInnerHTML` for a style/script block (even Carbon table row HTML), the inner HTML won't carry a nonce — Carbon `v1.100` is nonce-agnostic by default. Not audited in spec.
- **Fix direction**:
  - T-031 acceptance MUST add: render `/admin/pg-viewer/__force_error` (dev-only route that throws) and assert the error page still carries the CSP header AND nonce-bearing scripts. Use Playwright network tab to confirm no blocked-script console errors.
  - T-031 acceptance MUST add: grep `frontend/src/components/admin/pg-viewer/**` for `dangerouslySetInnerHTML` — if any hit, document how nonce is propagated (or refuse to merge).
  - Document in plan §5a that `global-error.tsx` under `/admin/pg-viewer` must use Carbon-standard error components only (no third-party that ships inline scripts).

---

### 🟡 MEDIUM

#### R3-M1 — Purger role `login + CONNECTION LIMIT 2` — password-leak blast radius still includes total audit wipe
- **Location**: `data-model.md:249`. `aikm_audit_purger` has `LOGIN PASSWORD … CONNECTION LIMIT 2` and owns every partition.
- **Threat model gap**: if `PG_AUDIT_PURGER_PASSWORD` leaks (build artefact, cron env export, developer laptop), an attacker with network access to PG can:
  - `DROP TABLE pg_viewer_audit_log_*` — wipe 100% of forensic trail.
  - `DROP TABLE pg_viewer_audit_log` CASCADE — kill parent + all children.
  - NOT modify individual rows (no UPDATE/DELETE grant), so point-edit is blocked — good.
  - NOT exfil data (no SELECT), so cannot read audit history before wiping — good.
- **What's documented**: 90-day rotation (`quickstart.md §9:354-380`). Pg_hba subnet restriction is aspirational only (R2-M3 still accepted). If the purger DSN is used in a cron on 192.168.1.11 host (not in a container), the `.env` file must be `chmod 600 root:root` — not in spec.
- **Fix direction (non-blocking)**:
  - Document threat model in `plan.md` risk row (equivalent to "superuser leak on purger scope"): expected blast radius = total audit-history loss; acceptable because audit is append-only, NOT integrity-signed; wiping != tampering-undetected.
  - `quickstart.md §10a` should `chmod 600 /etc/aikm/.env` + explicit note. Missing today.
  - Consider `NOLOGIN` + `SET ROLE aikm_audit_purger` via a wrapper (postgres-only), but that reintroduces superuser dependency — not recommended.

#### R3-M2 — `information_schema` still readable from `aikm_viewer`; `pg_catalog.pg_proc.prosrc` leaks SECURITY DEFINER function bodies
- **Location**: `data-model.md:76-77` explicitly `GRANT USAGE ON SCHEMA information_schema, pg_catalog TO aikm_viewer`. PUBLIC has default SELECT on `information_schema.columns`.
- **Attack surface**: An XSS pivot OR a leaked aikm_viewer password lets `SELECT column_name FROM information_schema.columns WHERE table_name='users'` → enumerates `password_hash`, `password_salt`, etc. R2 M6 accepted this — but `pg_proc.prosrc` is worse: it exposes FUNCTION BODIES, including any future SECURITY DEFINER function a DB engineer writes with hardcoded secrets. R2 M6 fix direction suggested "nightly CI grep `prosrc` for /password|token|secret/i" — NOT in T-041 or T-044 acceptance.
- **Fix direction**:
  - Add to T-044 (grant audit) acceptance: `SELECT proname FROM pg_proc WHERE prosecdef=true AND prosrc ~* '(password|secret|token|api_key)'` returns 0 rows → fail CI if non-zero.
  - Consider `REVOKE SELECT ON pg_proc FROM PUBLIC` — but this will break most admin tools; leave accepted.

#### R3-M3 — SQL editor transaction scope: nested `SET LOCAL` override
- **Location**: `spec.md FR-014` + `plan.md:42` — `BEGIN; SET LOCAL statement_timeout = '10s'; <validated SQL>`.
- **Subtle issue**: If a validated inner SQL contains e.g. `SELECT 1 FROM (SELECT set_config('statement_timeout','3600s',true)) _` the inner `set_config(..., true)` is local-to-transaction and **can override SET LOCAL within the same transaction** (Postgres semantics: SET LOCAL and `set_config(..., true)` stack; last-write-wins within the tx). T-016 validator denylist includes `set_config` in the function-name denylist? **Not listed** (`tasks.md:186` — denylist is dblink-family + pg_*_file + pg_sleep + lo_import/lo_export). `set_config` / `pg_catalog.set_config` NOT in denylist.
- **Impact**: Defense L4(c) (per-tx SET LOCAL) can be bypassed within a single tx via `set_config('statement_timeout','0',true)`. Role-level `statement_timeout='10s'` from L4(a) still holds AS A SESSION DEFAULT — but `set_config(..., is_local=true)` trumps it within the tx. Third layer asyncpg `command_timeout=10` still caps wall-clock → 408 fires even if PG sleeps. **So net impact: no data exfil, just potential resource waste until command_timeout fires. DoS risk, not secrecy risk.**
- **Fix direction**:
  - Add `set_config`, `pg_catalog.set_config`, and `current_setting` (no, current_setting is read-only — fine) to the T-016 forbidden function denylist.
  - Add T-016 test: `SELECT set_config('statement_timeout','0',true)` → reject.
  - Add T-022 defense-in-depth: after `SET LOCAL`, assert `SHOW statement_timeout` returns `10s` before executing user SQL (adds 1 ms, catches any residual drift).

---

### 🔵 LOW

- **R3-L1** `lc_messages` still unset on T-010 engine (R2-M7 leftover). Non-English error messages could smuggle role/table names past the regex. Add `SET lc_messages='C'` to T-010 connect-hook.
- **R3-L2** `/etc/aikm/.env` not spec'd as `chmod 600`. Operator footgun. Add to quickstart §2a.
- **R3-L3** `contracts/pg-viewer-api.yaml` missing `/csp-violations` path (duplicate of R3-H1 — noted here for OpenAPI hygiene).

---

## Go/No-Go for Phase 5 Day 1

**GO** for: T-001 (DB env wiring), T-002 (settings), T-002.5 (JWT-secret startup check), T-003 (data-model types), T-010 (engine), T-011 (introspect), T-012 (query builder), T-013 (redaction), T-014 (audit writer), T-014.5 (PII redactor), T-014.6 (rate limiter), T-015 (CSV exporter), T-016 (SQL validator). **None of R3 findings block the data-path critical chain.**

**HOLD** T-031 (CSP frontend) + T-046 (CSP reporter endpoint) until R3-H1 + R3-H2 acceptance bullets are amended. These run in parallel and do not block backend progress.

**RECOMMEND** adding R3-M3 (set_config denylist) to T-016 before it closes — 5-min fix; prevents a real (if low-impact) DoS vector.

---

## Summary

- **R2 verification**: 10/10 M-series verified (8 fixed, 1 partial-accepted, 1 risk-accepted minor), 3/3 housekeeping (R2-H1/H2/N1) fixed, 0 regressed.
- **New findings**: 2 HIGH, 3 MEDIUM, 3 LOW. 0 CRITICAL.
- **Residual accepted risks**: JWT-in-localStorage (H4, CSP-compensated); pg_hba subnet (R2-M3, awaiting ops); information_schema enumeration (R2-M6 + R3-M2).
- **Top 3 pre-merge fixes**: (1) add `/csp-violations` to OpenAPI + define Redis-down degrade-and-log posture (R3-H1); (2) add error-page CSP coverage to T-031 acceptance (R3-H2); (3) add `set_config` to T-016 denylist (R3-M3).

**Verdict: CONDITIONAL_YES — Phase 5 may start on the backend/data path today. CSP tasks wait for the two HIGH-finding acceptance edits (small, expected to land in <1 day).**
