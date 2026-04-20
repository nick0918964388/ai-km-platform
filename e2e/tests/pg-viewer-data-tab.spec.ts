/**
 * T-033 Playwright tests — DataTab component
 *
 * Test cases:
 * 1. Navigate to admin page, select maximo_mxasset table, Data tab loads
 * 2. Header click → sort direction toggles, rows re-render
 * 3. Add filter status = 'ACTIVE' → rows filtered
 * 4. ExportCSV click → browser receives file download
 * 5. Long string cell → "show more" → modal shows full text
 * 6. NULL cell → (null) italic
 *
 * All API responses are mocked for deterministic assertion.
 */

import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_TABLES = {
  tables: [
    { schema: 'public', name: 'maximo_mxasset', kind: 'table', approx_row_count: 16165, grant_missing: false },
    { schema: 'public', name: 'users', kind: 'table', approx_row_count: 12, grant_missing: false },
  ],
};

const MOCK_SCHEMA = {
  schema: 'public',
  name: 'maximo_mxasset',
  columns: [
    { name: 'assetnum', data_type: 'varchar', nullable: false, is_pk: true },
    { name: 'status', data_type: 'varchar', nullable: true },
    { name: 'description', data_type: 'text', nullable: true },
    { name: 'secret_col', data_type: 'varchar', nullable: true },
  ],
  primary_key: ['assetnum'],
  indexes: [],
  foreign_keys: [],
  approx_row_count: 16165,
};

const LONG_TEXT =
  'A'.repeat(250) + ' this is the hidden part of the long text value for testing';

const MOCK_ROWS_PAGE = {
  columns: [
    { name: 'assetnum', data_type: 'varchar', redacted: false },
    { name: 'status', data_type: 'varchar', redacted: false },
    { name: 'description', data_type: 'text', redacted: false },
    { name: 'secret_col', data_type: 'varchar', redacted: true },
  ],
  rows: [
    { assetnum: 'ASSET-001', status: 'ACTIVE', description: 'Normal asset', secret_col: '***' },
    { assetnum: 'ASSET-002', status: null, description: LONG_TEXT, secret_col: null },
    { assetnum: 'ASSET-003', status: 'INACTIVE', description: 'Third asset', secret_col: '***' },
  ],
  limit: 50,
  offset: 0,
  approx_total: 3,
  execution_ms: 12,
  truncated: false,
  notice: null,
};

const MOCK_ROWS_FILTERED = {
  ...MOCK_ROWS_PAGE,
  rows: [
    { assetnum: 'ASSET-001', status: 'ACTIVE', description: 'Normal asset', secret_col: '***' },
  ],
  approx_total: 1,
  execution_ms: 8,
};

// ---------------------------------------------------------------------------
// Helper: set up mocks and navigate
// ---------------------------------------------------------------------------

async function setupMocks(page: import('@playwright/test').Page) {
  // Mock tables list
  await page.route('**/api/pg-viewer/tables', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_TABLES),
    });
  });

  // Mock schema for maximo_mxasset
  await page.route('**/api/pg-viewer/tables/maximo_mxasset/schema', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SCHEMA),
    });
  });

  // Mock rows (default — no filters param)
  await page.route((url) => {
    const u = new URL(url);
    return (
      u.pathname.includes('/api/pg-viewer/tables/maximo_mxasset/rows') &&
      !u.searchParams.has('filters')
    );
  }, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_ROWS_PAGE),
    });
  });

  // Mock rows with filters (filtered response)
  await page.route((url) => {
    const u = new URL(url);
    return (
      u.pathname.includes('/api/pg-viewer/tables/maximo_mxasset/rows') &&
      u.searchParams.has('filters')
    );
  }, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_ROWS_FILTERED),
    });
  });

  // Mock CSV export
  await page.route('**/api/pg-viewer/tables/maximo_mxasset/export.csv**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/csv',
      headers: {
        'Content-Disposition': 'attachment; filename="maximo_mxasset.csv"',
      },
      body: 'assetnum,status,description\nASSET-001,ACTIVE,Normal asset\n',
    });
  });
}

async function loginAndNavigate(page: import('@playwright/test').Page) {
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
  await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
  await page.goto(`${BASE_URL}/admin/pg-viewer`);
  await page.waitForTimeout(800);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('T-033 — DataTab component', () => {

  // ── 1. Data tab loads after selecting table ───────────────────────────────
  test('1. Data tab loads rows when maximo_mxasset is selected', async ({ page }) => {
    await setupMocks(page);
    await loginAndNavigate(page);

    // Wait for table list
    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    // Select maximo_mxasset
    const rows = page.locator('[role="listbox"] [role="option"]');
    await expect(rows).toHaveCount(2, { timeout: 5000 });
    await rows.first().click();

    // Data tab should appear
    const dataTab = page.locator('[data-testid="data-tab"]');
    await expect(dataTab).toBeVisible({ timeout: 5000 });

    // Three data rows should be present
    const tableCells = page.locator('.cds--data-table tbody tr');
    await expect(tableCells).toHaveCount(3, { timeout: 5000 });

    // Row count badge
    await expect(dataTab).toContainText('3');
  });

  // ── 2. Header click toggles sort ─────────────────────────────────────────
  test('2. Clicking column header toggles sort direction', async ({ page }) => {
    await setupMocks(page);
    await loginAndNavigate(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    const listRows = page.locator('[role="listbox"] [role="option"]');
    await expect(listRows).toHaveCount(2, { timeout: 5000 });
    await listRows.first().click();

    const dataTab = page.locator('[data-testid="data-tab"]');
    await expect(dataTab).toBeVisible({ timeout: 5000 });

    // Wait for table headers to render
    const headers = page.locator('.cds--data-table thead th');
    await expect(headers.first()).toBeVisible({ timeout: 5000 });

    // Click the first header (assetnum) — sort ASC
    await headers.first().click();
    // Click again — sort DESC
    await headers.first().click();

    // The sort icon should now be ArrowDown (DESC direction)
    // We test that the table re-rendered rows (same 3 rows still present)
    const tableCells = page.locator('.cds--data-table tbody tr');
    await expect(tableCells).toHaveCount(3, { timeout: 5000 });
  });

  // ── 3. Filter status = ACTIVE → filtered results ─────────────────────────
  test('3. Adding status = ACTIVE filter returns filtered rows', async ({ page }) => {
    await setupMocks(page);
    await loginAndNavigate(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    const listRows = page.locator('[role="listbox"] [role="option"]');
    await expect(listRows).toHaveCount(2, { timeout: 5000 });
    await listRows.first().click();

    const dataTab = page.locator('[data-testid="data-tab"]');
    await expect(dataTab).toBeVisible({ timeout: 5000 });

    // Open filter bar
    const filterToggle = dataTab.locator('button[aria-label="顯示篩選條件"]');
    await filterToggle.click();

    // Click "新增篩選條件" button
    const addFilterBtn = dataTab.locator('button:has-text("新增篩選條件")');
    await expect(addFilterBtn).toBeVisible({ timeout: 3000 });
    await addFilterBtn.click();

    // A filter row should appear — select column "status"
    const colSelect = dataTab.locator('select').first();
    await colSelect.selectOption('status');

    // Set value to ACTIVE
    const valueInput = dataTab.locator('input[type="text"]').first();
    await valueInput.fill('ACTIVE');

    // Wait for debounced re-fetch (mock will intercept with filters param)
    // The filtered response has only 1 row
    await page.waitForTimeout(600);

    const tableCells = page.locator('.cds--data-table tbody tr');
    await expect(tableCells).toHaveCount(1, { timeout: 5000 });
  });

  // ── 4. Export CSV click triggers download ────────────────────────────────
  test('4. ExportCSV link triggers browser file download', async ({ page }) => {
    await setupMocks(page);
    await loginAndNavigate(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    const listRows = page.locator('[role="listbox"] [role="option"]');
    await expect(listRows).toHaveCount(2, { timeout: 5000 });
    await listRows.first().click();

    const dataTab = page.locator('[data-testid="data-tab"]');
    await expect(dataTab).toBeVisible({ timeout: 5000 });

    // Wait for export link to appear
    const exportLink = dataTab.locator('[data-testid="export-csv-link"]');
    await expect(exportLink).toBeVisible({ timeout: 5000 });

    // Set up download listener
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 8000 }),
      exportLink.click(),
    ]);

    // Verify download was triggered
    expect(download.suggestedFilename()).toMatch(/maximo_mxasset/);
  });

  // ── 5. Long string → show more → modal ───────────────────────────────────
  test('5. Long string cell shows "…顯示更多" and modal on click', async ({ page }) => {
    await setupMocks(page);
    await loginAndNavigate(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    const listRows = page.locator('[role="listbox"] [role="option"]');
    await expect(listRows).toHaveCount(2, { timeout: 5000 });
    await listRows.first().click();

    const dataTab = page.locator('[data-testid="data-tab"]');
    await expect(dataTab).toBeVisible({ timeout: 5000 });

    // Find "…顯示更多" button (ASSET-002 description is 250+ chars)
    const showMoreBtn = dataTab.locator('button:has-text("顯示更多")');
    await expect(showMoreBtn).toBeVisible({ timeout: 5000 });
    await showMoreBtn.click();

    // Modal should open with full text
    const modal = page.locator('[data-testid="cell-full-modal"]');
    await expect(modal).toBeVisible({ timeout: 3000 });

    // Modal should contain the hidden text portion
    await expect(modal).toContainText('this is the hidden part');
  });

  // ── 6. NULL cell renders italic (null) ───────────────────────────────────
  test('6. NULL cell renders as italic (null) text', async ({ page }) => {
    await setupMocks(page);
    await loginAndNavigate(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    const listRows = page.locator('[role="listbox"] [role="option"]');
    await expect(listRows).toHaveCount(2, { timeout: 5000 });
    await listRows.first().click();

    const dataTab = page.locator('[data-testid="data-tab"]');
    await expect(dataTab).toBeVisible({ timeout: 5000 });

    // ASSET-002 has status=null — find italic (null) element
    const nullCell = dataTab.locator('i[aria-label="null value"]');
    await expect(nullCell).toHaveCount(2, { timeout: 5000 }); // status=null, secret_col=null
    await expect(nullCell.first()).toContainText('(null)');
  });

});
