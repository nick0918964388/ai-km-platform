/**
 * T-032 Playwright tests — TableList component
 *
 * Test cases:
 * 1. List renders with mock data (3+ tables)
 * 2. Search box filters by substring
 * 3. Clicking a table sets URL ?table=foo
 * 4. grant_missing=true shows amber dot
 * 5. Keyboard navigation works (arrow keys + Enter)
 */

import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';

// ---------------------------------------------------------------------------
// Mock tables returned by /api/pg-viewer/tables
// ---------------------------------------------------------------------------
const MOCK_TABLES = {
  tables: [
    { schema: 'public', name: 'maximo_assets', kind: 'table', approx_row_count: 16165, grant_missing: false },
    { schema: 'public', name: 'maximo_workorders', kind: 'table', approx_row_count: 10742, grant_missing: false },
    { schema: 'public', name: 'maximo_fault_reports', kind: 'table', approx_row_count: 676, grant_missing: true },
    { schema: 'public', name: 'users', kind: 'table', approx_row_count: 12, grant_missing: false },
    { schema: 'public', name: 'pg_viewer_audit', kind: 'table', approx_row_count: 0, grant_missing: false },
  ],
};

// ---------------------------------------------------------------------------
// Helper: log in and navigate to pg-viewer with mocked API
// ---------------------------------------------------------------------------
async function setupWithMockTables(page: import('@playwright/test').Page) {
  // Mock the tables endpoint before navigating
  await page.route('**/api/pg-viewer/tables', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_TABLES),
    });
  });

  // Log in
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
  await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });

  // Navigate to pg-viewer
  await page.goto(`${BASE_URL}/admin/pg-viewer`);
  await page.waitForTimeout(1000);
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

test.describe('T-032 — TableList component', () => {

  // ── 1. List renders with mock data ────────────────────────────────────────
  test('1. Renders table list with 5 mock tables', async ({ page }) => {
    await setupWithMockTables(page);

    // The aside should be visible
    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    // At least 3 table rows visible (mock has 5)
    const rows = page.locator('[role="listbox"] [role="option"]');
    await expect(rows).toHaveCount(5, { timeout: 5000 });

    // Row count badges should appear
    // 16165 → "16k", 10742 → "11k", 676 → "676", 12 → "12", 0 → "0"
    await expect(aside).toContainText('16k');
    await expect(aside).toContainText('676');
  });

  // ── 2. Search filters by substring ───────────────────────────────────────
  test('2. Search box filters table list by substring', async ({ page }) => {
    await setupWithMockTables(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    // Wait for rows to appear
    const rows = page.locator('[role="listbox"] [role="option"]');
    await expect(rows).toHaveCount(5, { timeout: 5000 });

    // Type in search box
    const searchInput = aside.locator('input[type="search"]');
    await searchInput.fill('maximo');

    // After debounce/deferred value, only maximo_* tables should show
    await expect(rows).toHaveCount(3, { timeout: 2000 });

    // Verify the visible ones are maximo_*
    await expect(aside).toContainText('maximo_assets');
    await expect(aside).toContainText('maximo_workorders');
    await expect(aside).toContainText('maximo_fault_reports');

    // Non-maximo tables should be hidden
    await expect(aside.locator('text=users')).toHaveCount(0);
  });

  // ── 3. Clicking a table sets URL ?table=foo ───────────────────────────────
  test('3. Clicking a table row updates URL query param ?table=', async ({ page }) => {
    await setupWithMockTables(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    // Wait for the list to populate
    const rows = page.locator('[role="listbox"] [role="option"]');
    await expect(rows).toHaveCount(5, { timeout: 5000 });

    // Click the first row (maximo_assets)
    const firstRow = rows.first();
    await firstRow.click();

    // URL should now contain ?table=public.maximo_assets (or encoded form)
    await expect(page).toHaveURL(/table=/, { timeout: 3000 });
  });

  // ── 4. grant_missing shows amber dot ─────────────────────────────────────
  test('4. grant_missing=true shows amber indicator dot', async ({ page }) => {
    await setupWithMockTables(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    // Wait for rows
    await expect(page.locator('[role="listbox"] [role="option"]')).toHaveCount(5, { timeout: 5000 });

    // maximo_fault_reports has grant_missing=true → amber dot should appear
    const amberDot = page.locator('[data-testid="grant-missing-dot"]');
    await expect(amberDot).toHaveCount(1, { timeout: 3000 });

    // Verify tooltip text
    await expect(amberDot).toHaveAttribute('title', 'no SELECT grant — operator action needed');
  });

  // ── 5. Keyboard navigation ────────────────────────────────────────────────
  test('5. Keyboard navigation: ArrowDown moves focus, Enter selects', async ({ page }) => {
    await setupWithMockTables(page);

    const aside = page.locator('aside[aria-label="資料表列表"]');
    await expect(aside).toBeVisible({ timeout: 8000 });

    const listbox = aside.locator('[role="listbox"]');
    await expect(listbox).toBeVisible({ timeout: 5000 });

    // Wait for rows to render
    await expect(page.locator('[role="listbox"] [role="option"]')).toHaveCount(5, { timeout: 5000 });

    // Focus the listbox
    await listbox.focus();

    // Press ArrowDown twice to move to second row
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');

    // Press Enter to select — URL should update
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/table=/, { timeout: 3000 });
  });

});
