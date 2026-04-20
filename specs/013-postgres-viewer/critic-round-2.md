# Critic Round 2 — 013-postgres-viewer

**Reviewer angle**: Verify round-1 fixes + catch new inconsistencies introduced by the planner's round-2 edits.
**Date**: 2026-04-20
**Reviewed**: spec.md, research.md, plan.md, data-model.md, contracts/pg-viewer-api.yaml, tasks.md, quickstart.md, critic-round-1.md

## Verdict: CONDITIONAL_YES (proceed, but fix 3 HIGH before T-020/T-036 commit)

- Round-1 findings: **11/11 VERIFIED_FIXED** (4 CRITICAL + 7 HIGH).
- New round-2 findings: **0 CRITICAL, 3 HIGH, 5 MEDIUM, 4 LOW**.
- Phase 5 implementation: **YES — green-light**, with mandatory HIGH fixes during T-020 / T-036 / T-042. No blockers require re-planning.

---

## Part 1 — Verification Table (round-1 findings)

| ID | Title | Status | Evidence |
|---|---|---|---|
| C-1 | psycopg v2/v3 confusion | VERIFIED_FIXED | `plan.md:12,170`, `research.md:134-146` D-3 bridge rule, `tasks.md:39` T-002 requirements dep, `tasks.md:98-103` T-012 acceptance asserts `as_string(conn)` + NO Composed-to-asyncpg |
| C-2 | auto-LIMIT subquery bug | VERIFIED_FIXED | `spec.md:139` FR-014.6 "wrap not detect-and-append", `research.md:230` §SQL Static Analysis step 6, `tasks.md:174-205` T-016 acceptance covers subquery-LIMIT + top-level LIMIT>1000, `contracts:175-181` POST /sql description, `quickstart.md:212-217` |
| C-3 | statement_timeout under asyncpg | VERIFIED_FIXED | `spec.md:131` FR-012 three mechanisms, `plan.md:60` L4 three layers, `research.md:150-170` D-4, `data-model.md:181-183` ALTER ROLE, `tasks.md:75,82` T-010 integration test `pg_sleep(30) ≤ 11s` |
| C-4 | raw_sql audit PII | VERIFIED_FIXED | `spec.md:142,148-155` FR-016 + FR-017a, `data-model.md:127-145` redactor code, `tasks.md:118,133-148` T-014 + T-014.5 |
| H-1 | GET /audit task missing | VERIFIED_FIXED | `tasks.md:215,223` T-020 scope explicitly lists `GET /audit` + `AuditEntry`; `contracts:390-409` AuditEntry schema present |
| H-2 | Pydantic models missing | VERIFIED_FIXED | `tasks.md:265-275` T-030 scope adds `backend/app/schemas/pg_viewer.py` with 9 models + CI diff test |
| H-3 | Validator test matrix | VERIFIED_FIXED | `tasks.md:184-203` T-016 acceptance covers nested comments, MySQL hints, mixed-case, BOM/NFC, Cyrillic, UNION, pg_sleep, lo_import, COPY TO PROGRAM, \\copy meta, quoted-string literal, CTE-headed DELETE |
| H-4 | 408 vs 422 mapping | VERIFIED_FIXED | `spec.md:167` FR-064 SQLSTATE→HTTP table, `tasks.md:143-146` T-014.5 acceptance, `tasks.md:222` T-020 acceptance asserts role-name/DSN/DETAIL/HINT never leak |
| H-5 | clamp vs reject LIMIT>1000 | VERIFIED_FIXED | Decision = REJECT 400 documented consistently: `spec.md:95,132,139`, `plan.md:59`, `tasks.md:175,200`, `contracts:179-181,212`, `quickstart.md:212-217` |
| H-6 | REVOKE CREATE from PUBLIC | VERIFIED_FIXED | `data-model.md:204` `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, `research.md:107` |
| H-7 | audit write on tx rollback | VERIFIED_FIXED | `spec.md:142` FR-016 "independent transaction", `plan.md:63` L7, `tasks.md:117-123` T-014 acceptance includes "forces outer handler to raise after write_audit returns — row must persist" |

Stats: **11/11 round-1 findings VERIFIED_FIXED. 0 regressions.**

---

## Part 2 — New Round-2 Findings

### HIGH (fix before merge, not before phase 5)

- [ ] **R2-H1 — `users_public` view column list inconsistent between spec/data-model and the FR-062 contract sentence.**
  - `spec.md:158` (FR-062): "exposing safe columns only (`id, email, display_name, account_level, created_at, last_login_at`)".
  - `data-model.md:217-219`: `SELECT id, email, display_name, account_level, created_at, last_login_at FROM public.users` — matches spec.
  - `data-model.md:109-110` `HIDDEN_COLUMNS` still lists `("users_public", "email")` as hidden — CONTRADICTS the spec which says `email` IS a safe column of `users_public`.
  - `quickstart.md:280` curl example projects `SELECT id, email FROM users_public` — expects email visible. If T-013 wires the HIDDEN rule, this curl returns an error or email gets dropped.
  - Consequence: T-013 will either (a) enforce HIDDEN and break the documented smoke test, or (b) be silently diverged from the redaction module. Either way CI breaks or redaction rule dies.
  - Fix direction: remove `("users_public", "email")` from `HIDDEN_COLUMNS` in data-model.md:109 OR change the spec wording. Decide now.

- [ ] **R2-H2 — Contract OpenAPI still describes 429 only for `/rows`, `/export.csv`, `/sql` — missing on `/tables` and `/tables/{table}/schema`, but FR-063 rate-limiter scope is ambiguous.**
  - `spec.md:161` FR-063: "`POST /api/pg-viewer/sql` … 30/min … `/rows` and `/export.csv` 60/min/user". No mention of `/tables` or `/schema`.
  - `tasks.md:151` T-014.6 scope: only `/sql` and `/rows` + `/export.csv`.
  - `contracts/pg-viewer-api.yaml`: 429 documented on `/rows` (110-112), `/export.csv` (148-152), `/sql` (216-220) — but `/tables` (23-43) and `/schema` (44-60) have no 429 documented.
  - Ambiguity: Are `/tables` and `/schema` truly unlimited? A bash loop on /tables with N tables triggers N introspection queries per request — could melt pool even without 429.
  - Fix direction: make a decision. Either (a) add `/tables` + `/schema` under the 60/min bucket and document in contract + FR-063, or (b) explicitly state in FR-063 that `/tables` and `/schema` are unlimited and why (they hit 5-min LRU cache, so cost is bounded).

- [ ] **R2-H3 — `tasks.md` "Parallel-safe Task Count" and "Done Criteria" STILL say "Total tasks: 23" and "All T-001 … T-042 closed" — did not get updated for the new T-002.5, T-014.5, T-014.6, T-043, T-044, T-045.**
  - `tasks.md:511`: "Total tasks: **23** (T-001 … T-042, numbering with gaps). New since clarification pass: T-016, T-022, T-036, T-037."
  - `tasks.md:523`: "All T-001 … T-042 closed (including T-016 / T-022 / T-036 / T-037)."
  - `critic-round-1.md:36` Resolution states "Total now **30 tasks**".
  - Actual count (per file): T-001, 002, 002.5, 003, 010, 011, 012, 013, 014, 014.5, 014.6, 015, 016, 020, 021, 022, 030, 031, 032, 033, 034, 035, 036, 037, 040, 041, 042, 043, 044, 045 = **30**.
  - Consequence: Done Criteria is missing T-043/T-044/T-045 (retention runbook, CI pipeline update, observability) — a deploy could pass "all T-042 closed" while skipping observability metrics and nightly grant audit.
  - Fix direction: update line 511 to "30 tasks" and line 523 to "All T-001 … T-045 closed". Add T-043, T-044, T-045 to the done checklist.

### MEDIUM

- [ ] **R2-M1 — Dependency graph does NOT mention T-002.5, T-014.5, T-014.6, T-043, T-044, T-045.**
  - `tasks.md:476-498` dependency graph only shows T-001..T-042 with no new nodes.
  - Parallel batches (501-506) also silent on them.
  - These tasks are orphaned from the graph even though the parent/child relationships are listed in each task's "輸入". Engineer reading the graph to pick next task will miss them.
  - Fix: add T-002.5 parallel with T-002; T-014.5 + T-014.6 parallel with T-014; T-043 after T-042; T-044 parallel with T-042; T-045 as leaf after T-020.

- [ ] **R2-M2 — `Rollback Procedure` in tasks.md:517 still says `DROP TABLE IF EXISTS pg_viewer_audit_log` but data-model.md:272 now declares it PARTITIONED; the parent-table DROP in PG 14+ requires CASCADE to also drop the monthly partitions.**
  - `tasks.md:517`: `psql -c "DROP TABLE IF EXISTS pg_viewer_audit_log; DROP ROLE IF EXISTS aikm_viewer;"`.
  - `quickstart.md:313` correctly uses `DROP TABLE IF EXISTS pg_viewer_audit_log CASCADE`.
  - Consequence: during emergency rollback, the tasks-file version errors out, leaving orphan partitions + still-linked parent.
  - Fix: add `CASCADE` to tasks.md:517.

- [ ] **R2-M3 — `PG_VIEWER_RATE_LIMIT_ROWS` env var documented in plan.md:16 + tasks.md T-002 scope but spec.md FR-063 never references the env knob — so ops reading spec alone cannot discover it's tunable.**
  - `plan.md:16`, `tasks.md:39`, `tasks.md:154` all mention `PG_VIEWER_RATE_LIMIT_SQL` and `PG_VIEWER_RATE_LIMIT_ROWS`.
  - `spec.md:161` FR-063 hard-codes 30/min and 60/min with no env-var reference.
  - Fix: extend FR-063 to mention both env vars and that they tune the two bucket sizes.

- [ ] **R2-M4 — T-042 acceptance says migration split runs 001 as postgres + 002 as aikm, but tasks.md rollback step (517) uses `psql -c` without specifying the user.**
  - Rollback with default user likely lands on aikm — cannot `DROP ROLE` (requires postgres).
  - Fix: `tasks.md:517` specify `psql -U postgres -d aikm -c …`.

- [ ] **R2-M5 — `users_public` view column list doesn't include `username` field that existing app code may reference.**
  - Curl examples in quickstart.md only project `id, email, display_name` — fine.
  - But if any existing NL2SQL example or downstream frontend code joins `users.username`, they'll be broken via this view. Not a v1 regression because other code uses the `aikm` role not `aikm_viewer`, but worth noting.
  - Fix: add one sentence to spec.md FR-062 clarifying that `users_public` is for pg-viewer ONLY; main app continues to use `users` via `aikm` role.

### LOW / NITS

- [ ] **R2-L1 — `contracts/pg-viewer-api.yaml:355,388` SqlResult.notice description says `"LIMIT 1000 auto-appended"` but spec.md FR-014.6 / tasks.md T-022 expect `"LIMIT 1000 server-wrap applied"`.** Cosmetic divergence in human-readable string; breaks any Playwright assertion on the exact text.
- [ ] **R2-L2 — `contracts/pg-viewer-api.yaml:384` SqlResult.truncated description says "true if the server auto-appended `LIMIT 1000` or the user's LIMIT was clamped down"** — but clamp was rejected in favor of reject-400. Wording is stale. Fix: "true if the server wrap capped the result at 1000 rows".
- [ ] **R2-L3 — `quickstart.md:174` positive example paste reads `SELECT * FROM users LIMIT 5`** — but `aikm_viewer` has NO SELECT on `users` (FR-062 option-b). Smoke test will 42501 → 403. Change to `SELECT * FROM users_public LIMIT 5`.
- [ ] **R2-L4 — `quickstart.md:188` comment claims `notice≈"LIMIT 1000 auto-appended"`** — inconsistent with wrap language used elsewhere. Same fix as R2-L1 — pick one phrase ("LIMIT 1000 server-wrap applied") and propagate everywhere.

---

## Part 3 — Cross-file grep audit (consistency spot-checks)

| Check | Result |
|---|---|
| `psycopg2` mentioned anywhere as import / dep? | NO — only `psycopg[binary]>=3.1` |
| `SELECT * FROM users` as positive path anywhere? | **YES (R2-L3)** — quickstart.md:174 needs `users_public` |
| "clamp" language still present where reject is policy? | **YES (R2-L2)** — contract SqlResult.truncated description |
| `users_public` view referenced in both migration + contract + quickstart? | Migration ✓, quickstart ✓, contract — NO mention (the view isn't listed as a TableSummary kind), but OpenAPI doesn't need to enumerate specific tables, so acceptable |
| T-002.5 / T-014.5 / T-014.6 / T-043 / T-044 / T-045 in dependency graph? | **NO (R2-M1)** |
| Task count statement accurate? | **NO (R2-H3)** |
| 429 documented in OpenAPI for all rate-limited endpoints? | Partial — `/tables` + `/schema` ambiguous (R2-H2) |
| `grant_missing` documented as error case in spec.md? | Implicit via FR-064 42501→403 mapping; OpenAPI adds `grant_missing:true` boolean on TableSummary. Defensible. |

---

## Part 4 — Should this proceed to Phase 5 implementation?

**YES — proceed.**

Rationale:
- All 4 CRITICAL + 7 HIGH from round-1 are genuinely fixed in-spec (not just in the Resolution block). Cross-file consistency holds on the security-critical items (psycopg bridge rule, three-layer timeout, LIMIT wrap, PII redaction, independent audit tx, REVOKE PUBLIC).
- The 3 new HIGH findings (R2-H1, R2-H2, R2-H3) are cosmetic / scope-clarification issues that do NOT change the threat model or the implementation topology. They can be fixed inside T-020 / T-036 / T-042 PR commits.
- No new CRITICAL discovered.
- New task insertions (T-002.5, T-014.5, T-014.6, T-043, T-044, T-045) are internally coherent; only the graph/count metadata is stale (R2-M1, R2-H3).

**Mandatory fixes before merging the feature branch** (not before starting implementation):
1. R2-H1 (users_public.email HIDDEN_COLUMNS drift) — will break T-013 CI.
2. R2-H3 (task count "23" → "30"; done criteria → T-045).
3. R2-M1 (add new tasks to dependency graph).

**Nice-to-have during implementation**:
4. R2-H2 (decide `/tables` + `/schema` rate-limit policy).
5. R2-L1 + R2-L2 + R2-L4 (normalize "server-wrap applied" string across contract/spec/quickstart).
6. R2-L3 (quickstart curl sample → `users_public`).
7. R2-M2, R2-M3, R2-M4, R2-M5.

No planner re-spin required. Implementation can start immediately on T-002 / T-002.5 / T-003 in parallel.


---

## Resolution (P9 round-3 prep, 2026-04-20)

Consolidated pointer for the round-2 main report. All findings mapped in `critic-round-2-security.md ## Resolution` and `critic-round-2-ops.md ## Resolution`. Nothing left RISK_ACCEPTED or DEFERRED.

Task-count impact: +1 new task (T-046). Total tasks now 31. Critical path unchanged. Ready for round-3 critic sweep.
