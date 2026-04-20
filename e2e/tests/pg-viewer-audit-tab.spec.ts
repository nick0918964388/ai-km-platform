/**
 * T-035 Playwright tests — AuditTab component
 *
 * Test cases:
 * 1. Audit tab renders with mock data
 * 2. Filter by status='error' → only error rows visible
 * 3. Sort by created_at toggles ASC/DESC
 * 4. Click raw_sql cell → modal shows full text
 * 5. Pagination change (page 2) → loads next batch
 */

import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';

// ---------------------------------------------------------------------------
// Mock audit entries
// ---------------------------------------------------------------------------

const NOW = new Date('2026-04-20T10:00:00Z').toISOString();
const ONE_MIN_AGO = new Date('2026-04-20T09:59:00Z').toISOString();
const TWO_MIN_AGO = new Date('2026-04-20T09:58:00Z').toISOString();

const MOCK_AUDIT_PAGE1 = {
  entries: [
    {
      id: 1,
      user_id: 'u1',
      user_email: 'admin@example.com',
      query_type: 'sql_editor',
      table_name: null,
      action: 'sql_editor',
      row_count: 42,
      execution_ms: 120,
      status: 'ok',
      raw_sql: 'SELECT * FROM maximo_assets WHERE status = \'OPERATING\'',
      error_message: null,
      created_at: NOW,
    },
    {
      id: 2,
      user_id: 'u2',
      user_email: 'user@example.com',
      query_type: 'table_browse',
      table_name: 'maximo_workorders',
      action: 'table_browse',
      row_count: 0,
      execution_ms: 55,
      status: 'error',
      raw_sql: null,
      error_message: 'permission denied for table maximo_workorders',
      created_at: ONE_MIN_AGO,
    },
    {
      id: 3,
      user_id: 'u1',
      user_email: 'admin@example.com',
      query_type: 'schema',
      table_name: 'users',
      action: 'schema',
      row_count: null,
      execution_ms: 30,
      status: 'ok',
      raw_sql: null,
      error_message: null,
      created_at: TWO_MIN_AGO,
    },
  ],
  total: 3,
};

const MOCK_AUDIT_PAGE2 = {
  entries: [
    {
      id: 4,
      user_id: 'u3',
      user_email: 'analyst@example.com',
      query_type: 'sql_editor',
      table_name: null,
      action: 'sql_editor',
      row_count: 10,
      execution_ms: 200,
      status: 'timeout',
      raw_sql: 'SELECT count(*) FROM maximo_assets GROUP BY siteid',
      error_message: 'statement timeout',
      created_at: new Date('2026-04-20T09:55:00Z').toISOString(),
    },
  ],
  total: 4,
};

const MOCK_TABLES = {
  tables: [
    { schema: 'public', name: 'maximo_assets', kind: 'table', approx_row_count: 100, grant_missing: false },
  ],
};

// ---------------------------------------------------------------------------
// Helper: login + navigate to pg-viewer with mocked API
// ---------------------------------------------------------------------------

async function setupPgViewer(
  page: import('@playwright/test').Page,
  auditMock: object = MOCK_AUDIT_PAGE1
) {
  // Mock tables
  await page.route('**/api/pg-viewer/tables', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TABLES) });
  });

  // Mock audit — default page 1
  await page.route('**/api/pg-viewer/audit**', (route) => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get('offset') ?? 0);
    if (offset > 0) {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AUDIT_PAGE2) });
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(auditMock) });
    }
  });

  // Login
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
  await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });

  await page.goto(`${BASE_URL}/admin/pg-viewer`);
  await page.waitForTimeout(800);
}

async function clickAuditTab(page: import('@playwright/test').Page) {
  const auditTabBtn = page.locator('[role="tab"]').filter({ hasText: 'Audit' });
  await expect(auditTabBtn).toBeVisible({ timeout: 8000 });
  await auditTabBtn.click();
  await page.waitForTimeout(600);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('T-035 — AuditTab', () => {

  // ── 1. Renders with mock data ──────────────────────────────────────────────
  test('1. Audit tab renders table with mock data', async ({ page }) => {
    await setupPgViewer(page);
    await clickAuditTab(page);

    // The audit table should be visible
    const table = page.locator('[data-testid="audit-table"]');
    await expect(table).toBeVisible({ timeout: 8000 });

    // All 3 mock rows should be present
    const rows = page.locator('[data-testid="audit-row"]');
    await expect(rows).toHaveCount(3, { timeout: 5000 });

    // Verify user emails appear
    await expect(table).toContainText('admin@example.com');
    await expect(table).toContainText('user@example.com');

    // Status tags
    const statusTags = page.locator('[data-testid="status-tag"]');
    await expect(statusTags.first()).toBeVisible();
  });

  // ── 2. Filter by status='error' ───────────────────────────────────────────
  test('2. Filter by status=error → only error rows visible', async ({ page }) => {
    // Provide mock that returns only error entries when status=error is set
    await page.route('**/api/pg-viewer/tables', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TABLES) });
    });

    const ERROR_ONLY = {
      entries: [MOCK_AUDIT_PAGE1.entries[1]], // the error entry
      total: 1,
    };

    await page.route('**/api/pg-viewer/audit**', (route) => {
      const url = new URL(route.request().url());
      const statusParam = url.searchParams.get('status');
      if (statusParam === 'error') {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ERROR_ONLY) });
      } else {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AUDIT_PAGE1) });
      }
    });

    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
    await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
    await page.goto(`${BASE_URL}/admin/pg-viewer`);
    await page.waitForTimeout(800);

    await clickAuditTab(page);

    // Initially 3 rows
    await expect(page.locator('[data-testid="audit-row"]')).toHaveCount(3, { timeout: 5000 });

    // Select 'error' in status filter
    const statusSelect = page.locator('[data-testid="filter-status"]');
    await expect(statusSelect).toBeVisible();
    await statusSelect.selectOption('error');

    // Wait for reload
    await page.waitForTimeout(600);

    // Now only 1 error row
    const rows = page.locator('[data-testid="audit-row"]');
    await expect(rows).toHaveCount(1, { timeout: 5000 });

    // Confirm it's the error entry
    await expect(rows.first()).toHaveAttribute('data-status', 'error');
  });

  // ── 3. Sort by created_at toggles ASC/DESC ────────────────────────────────
  test('3. Sort by created_at toggles ASC/DESC', async ({ page }) => {
    await setupPgViewer(page);
    await clickAuditTab(page);

    await expect(page.locator('[data-testid="audit-row"]')).toHaveCount(3, { timeout: 5000 });

    // The header "時間" column has aria-sort="descending" by default
    const timeHeader = page.locator('th[aria-sort]');
    await expect(timeHeader).toHaveAttribute('aria-sort', 'descending');

    // Click to toggle to ascending
    await timeHeader.click();
    await expect(timeHeader).toHaveAttribute('aria-sort', 'ascending');

    // Click again to toggle back to descending
    await timeHeader.click();
    await expect(timeHeader).toHaveAttribute('aria-sort', 'descending');
  });

  // ── 4. Click raw_sql → modal shows full text ──────────────────────────────
  test('4. Click raw_sql cell → modal shows full SQL text', async ({ page }) => {
    await setupPgViewer(page);
    await clickAuditTab(page);

    await expect(page.locator('[data-testid="audit-row"]')).toHaveCount(3, { timeout: 5000 });

    // Click the first raw_sql cell (entry id=1 has SQL)
    const sqlCell = page.locator('[data-testid="raw-sql-cell"]').first();
    await expect(sqlCell).toBeVisible({ timeout: 5000 });
    await sqlCell.click();

    // Modal should appear
    const modal = page.locator('[data-testid="sql-modal"]');
    await expect(modal).toBeVisible({ timeout: 3000 });

    // Full SQL text should be shown
    await expect(modal).toContainText("SELECT * FROM maximo_assets WHERE status = 'OPERATING'");

    // Close by clicking the × button
    const closeBtn = modal.locator('button[aria-label="關閉"]');
    await closeBtn.click();
    await expect(modal).not.toBeVisible({ timeout: 3000 });
  });

  // ── 5. Pagination change (page 2) → loads next batch ─────────────────────
  test('5. Pagination: next page loads second batch', async ({ page }) => {
    // Use a mock with total=4 so two pages of 10 still requires page navigation
    // We set pageSize to 10 (default) and total=4 means only 1 page normally.
    // So we need total > pageSize. Let's override with total=11 and provide 3 rows for p1.
    const BIG_MOCK = {
      entries: MOCK_AUDIT_PAGE1.entries,
      total: 11, // more than default page size 10
    };

    await page.route('**/api/pg-viewer/tables', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TABLES) });
    });

    await page.route('**/api/pg-viewer/audit**', (route) => {
      const url = new URL(route.request().url());
      const offset = Number(url.searchParams.get('offset') ?? 0);
      if (offset >= 10) {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AUDIT_PAGE2) });
      } else {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BIG_MOCK) });
      }
    });

    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
    await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
    await page.goto(`${BASE_URL}/admin/pg-viewer`);
    await page.waitForTimeout(800);

    await clickAuditTab(page);

    // Page 1: 3 rows, total shown as 11
    await expect(page.locator('[data-testid="audit-row"]')).toHaveCount(3, { timeout: 5000 });

    // Next page button should be enabled
    const nextBtn = page.locator('[data-testid="pagination-next"]');
    await expect(nextBtn).toBeVisible();
    await expect(nextBtn).not.toBeDisabled();

    await nextBtn.click();
    await page.waitForTimeout(600);

    // Page 2: 1 row from MOCK_AUDIT_PAGE2
    await expect(page.locator('[data-testid="audit-row"]')).toHaveCount(1, { timeout: 5000 });

    // Prev button now enabled
    const prevBtn = page.locator('[data-testid="pagination-prev"]');
    await expect(prevBtn).not.toBeDisabled();
  });

});
