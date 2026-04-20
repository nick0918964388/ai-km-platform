/**
 * T-034 Playwright tests — SchemaTab component
 *
 * Test cases:
 * 1. Schema tab for `public.users_public` renders all columns
 * 2. PK column row is visually highlighted (data-pk="true")
 * 3. FK link click navigates to referenced table (URL ?table= changes)
 * 4. 50-column wide table doesn't overflow viewport (horizontal scroll only within section)
 *
 * All tests mock the API for deterministic fixtures.
 */

import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_TABLES = {
  tables: [
    { schema: 'public', name: 'users_public', kind: 'table', approx_row_count: 42, grant_missing: false },
    { schema: 'public', name: 'orders', kind: 'table', approx_row_count: 500, grant_missing: false },
  ],
};

/** Schema for users_public — 4 columns, 1 PK, 1 index, 1 FK */
const MOCK_SCHEMA_USERS_PUBLIC = {
  schema: 'public',
  name: 'users_public',
  columns: [
    { name: 'id', data_type: 'integer', nullable: false, default: "nextval('users_public_id_seq'::regclass)", is_pk: true },
    { name: 'email', data_type: 'text', nullable: false, default: null, is_pk: false },
    { name: 'display_name', data_type: 'text', nullable: true, default: null, is_pk: false },
    { name: 'created_at', data_type: 'timestamp with time zone', nullable: false, default: 'now()', is_pk: false },
  ],
  primary_key: ['id'],
  indexes: [
    { name: 'users_public_pkey', definition: 'CREATE UNIQUE INDEX users_public_pkey ON public.users_public USING btree (id)', unique: true },
    { name: 'users_public_email_idx', definition: 'CREATE INDEX users_public_email_idx ON public.users_public USING btree (email)', unique: false },
  ],
  foreign_keys: [
    { column: 'id', foreign_table: 'orders', foreign_column: 'user_id' },
  ],
  approx_row_count: 42,
};

/** Wide-table schema with 50 columns for overflow test */
function buildWideSchema(tableName: string) {
  const columns = Array.from({ length: 50 }, (_, i) => ({
    name: `col_${String(i + 1).padStart(2, '0')}`,
    data_type: 'text',
    nullable: true,
    default: null,
    is_pk: i === 0,
  }));
  return {
    schema: 'public',
    name: tableName,
    columns,
    primary_key: ['col_01'],
    indexes: [],
    foreign_keys: [],
    approx_row_count: 0,
  };
}

// ---------------------------------------------------------------------------
// Helper: log in and set up mocked API + navigate to pg-viewer
// ---------------------------------------------------------------------------
async function setupWithMocks(
  page: import('@playwright/test').Page,
  targetTable: string,
  schemaFixture: object
) {
  // Mock tables list
  await page.route('**/api/pg-viewer/tables', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_TABLES),
    });
  });

  // Mock schema endpoint for the target table
  await page.route(`**/api/pg-viewer/tables/${encodeURIComponent(targetTable)}/schema`, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(schemaFixture),
    });
  });

  // Log in
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
  await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });

  // Navigate directly to pg-viewer with the target table selected
  await page.goto(`${BASE_URL}/admin/pg-viewer?table=${encodeURIComponent(targetTable)}`);
  await page.waitForTimeout(1000);

  // Activate Schema tab
  const schemaTab = page.locator('[role="tab"]', { hasText: 'Schema' });
  await expect(schemaTab).toBeVisible({ timeout: 8000 });
  await schemaTab.click();

  // Wait for schema tab panel to be active
  const schemaPanel = page.locator('#tabpanel-schema');
  await expect(schemaPanel).toBeVisible({ timeout: 5000 });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

test.describe('T-034 — SchemaTab component', () => {

  // ── 1. All columns render ──────────────────────────────────────────────────
  test('1. Schema tab for users_public renders all 4 columns', async ({ page }) => {
    await setupWithMocks(page, 'public.users_public', MOCK_SCHEMA_USERS_PUBLIC);

    const schemaPanel = page.locator('#tabpanel-schema');
    await expect(schemaPanel).toBeVisible({ timeout: 8000 });

    // Wait for data to load (spinner disappears)
    await expect(schemaPanel.locator('[data-testid="schema-tab"]')).toBeVisible({ timeout: 8000 });

    // All 4 column rows should be present
    const colRows = schemaPanel.locator('[data-testid^="col-row-"]');
    await expect(colRows).toHaveCount(4, { timeout: 5000 });

    // Verify specific column names appear
    await expect(schemaPanel).toContainText('id');
    await expect(schemaPanel).toContainText('email');
    await expect(schemaPanel).toContainText('display_name');
    await expect(schemaPanel).toContainText('created_at');

    // Verify data types appear
    await expect(schemaPanel).toContainText('integer');
    await expect(schemaPanel).toContainText('text');
    await expect(schemaPanel).toContainText('timestamp with time zone');
  });

  // ── 2. PK column is visually highlighted ──────────────────────────────────
  test('2. PK column row has data-pk="true" attribute (visual highlight)', async ({ page }) => {
    await setupWithMocks(page, 'public.users_public', MOCK_SCHEMA_USERS_PUBLIC);

    const schemaPanel = page.locator('#tabpanel-schema');
    await expect(schemaPanel.locator('[data-testid="schema-tab"]')).toBeVisible({ timeout: 8000 });

    // The "id" column is the PK — its row should have data-pk="true"
    const pkRow = schemaPanel.locator('[data-testid="col-row-id"][data-pk="true"]');
    await expect(pkRow).toHaveCount(1, { timeout: 5000 });

    // Non-PK rows should NOT have data-pk
    const emailRow = schemaPanel.locator('[data-testid="col-row-email"]');
    await expect(emailRow).toHaveCount(1);
    await expect(emailRow).not.toHaveAttribute('data-pk', 'true');

    // PK chip in PrimaryKey section
    const pkChip = schemaPanel.locator('[data-testid="pk-chip-id"]');
    await expect(pkChip).toBeVisible({ timeout: 3000 });
    await expect(pkChip).toContainText('id');
  });

  // ── 3. FK link navigates to referenced table ──────────────────────────────
  test('3. FK link click updates URL ?table= to referenced table', async ({ page }) => {
    // Also mock the schema for the referenced table "orders"
    await page.route('**/api/pg-viewer/tables/orders/schema', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ schema: 'public', name: 'orders', columns: [], primary_key: [], indexes: [], foreign_keys: [] }),
      });
    });

    await setupWithMocks(page, 'public.users_public', MOCK_SCHEMA_USERS_PUBLIC);

    const schemaPanel = page.locator('#tabpanel-schema');
    await expect(schemaPanel.locator('[data-testid="schema-tab"]')).toBeVisible({ timeout: 8000 });

    // FK link to "orders" should be visible
    const fkLink = schemaPanel.locator('[data-testid="fk-link-orders"]');
    await expect(fkLink).toBeVisible({ timeout: 5000 });

    // Click the FK link
    await fkLink.click();

    // URL should now contain ?table=orders
    await expect(page).toHaveURL(/table=orders/, { timeout: 5000 });
  });

  // ── 4. Wide table (50 columns) doesn't overflow viewport ──────────────────
  test('4. 50-column table uses horizontal scroll within section, not viewport overflow', async ({ page }) => {
    const WIDE_TABLE = 'public.wide_table';
    const wideSchema = buildWideSchema('wide_table');

    await page.route(`**/api/pg-viewer/tables/${encodeURIComponent(WIDE_TABLE)}/schema`, (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(wideSchema),
      });
    });

    // Add wide_table to the tables mock for this test
    await page.route('**/api/pg-viewer/tables', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tables: [
            ...MOCK_TABLES.tables,
            { schema: 'public', name: 'wide_table', kind: 'table', approx_row_count: 0, grant_missing: false },
          ],
        }),
      });
    });

    // Log in
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"], input[name="email"]', ADMIN_EMAIL);
    await page.fill('input[type="password"], input[name="password"]', ADMIN_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });

    await page.goto(`${BASE_URL}/admin/pg-viewer?table=${encodeURIComponent(WIDE_TABLE)}`);
    await page.waitForTimeout(1000);

    const schemaTab = page.locator('[role="tab"]', { hasText: 'Schema' });
    await expect(schemaTab).toBeVisible({ timeout: 8000 });
    await schemaTab.click();

    const schemaPanel = page.locator('#tabpanel-schema');
    await expect(schemaPanel.locator('[data-testid="schema-tab"]')).toBeVisible({ timeout: 8000 });

    // All 50 column rows should be present
    const colRows = schemaPanel.locator('[data-testid^="col-row-"]');
    await expect(colRows).toHaveCount(50, { timeout: 8000 });

    // The page itself must NOT have horizontal scroll (document.body should not overflow)
    const bodyOverflows = await page.evaluate(() => {
      return document.body.scrollWidth > document.documentElement.clientWidth;
    });
    expect(bodyOverflows, 'Page body must not overflow horizontally').toBe(false);

    // The columns table wrapper (overflowX: auto) should exist within the schema panel
    const overflowContainer = schemaPanel.locator('div[style*="overflow-x"]').first();
    await expect(overflowContainer).toBeVisible({ timeout: 3000 });
  });

});
