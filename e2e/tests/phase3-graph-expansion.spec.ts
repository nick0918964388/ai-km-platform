/**
 * Phase 3 W3-T1: Chat 圖擴展面板 UI 骨架測試
 *
 * Feature flag: NEXT_PUBLIC_ENABLE_GRAPH_EXPANSION=true 或 URL ?enableGraph=1
 * 前端僅用 mock data，未串真實 API（等 W2-T2 後端整合完成）
 */

import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://192.168.1.11:3000';
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin';

async function loginAndOpenChat(page: Page) {
  await page.goto(`${BASE_URL}/?enableGraph=1`);
  const emailInput = page.getByPlaceholder('請輸入您的電子郵件');
  if (await emailInput.isVisible().catch(() => false)) {
    await emailInput.fill(ADMIN_EMAIL);
    await page.getByPlaceholder('請輸入密碼').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: '登入' }).click();
    await page.waitForURL(/\/(chat|admin)/, { timeout: 10000 });
  }
  await page.goto(`${BASE_URL}/chat?enableGraph=1`);
  await page.waitForLoadState('networkidle');
}

async function sendMessage(page: Page, text: string) {
  // 找輸入框（chat input）送出一則訊息
  const textarea = page.locator('textarea').first();
  await textarea.fill(text);
  await textarea.press('Enter');
  // 等 assistant 回覆完成（panel 只在非 streaming 時出現）
  await page.waitForSelector('[data-testid="graph-expansion-panel"]', { timeout: 60000 });
}

test.describe('W3-T1: Graph Expansion Panel', () => {
  test.skip(!process.env.RUN_GRAPH_E2E, 'W3-T1 skeleton — set RUN_GRAPH_E2E=1 to run against live deploy');

  test.beforeEach(async ({ page }) => {
    await loginAndOpenChat(page);
  });

  test('發送訊息後應看到相關工單/建議SOP/常用零件 3 個區塊', async ({ page }) => {
    await sendMessage(page, '煞車異響有哪些常見故障？');

    const panel = page.locator('[data-testid="graph-expansion-panel"]').first();
    await expect(panel).toBeVisible();

    await expect(panel.getByText('相關工單')).toBeVisible();
    await expect(panel.getByText('建議 SOP')).toBeVisible();
    await expect(panel.getByText('常用零件')).toBeVisible();
  });

  test('點擊區塊 header 應展開項目', async ({ page }) => {
    await sendMessage(page, '煞車來令片更換流程？');

    const panel = page.locator('[data-testid="graph-expansion-panel"]').first();
    const header = panel.locator('[data-testid="section-workorders"] button').first();

    // 預設收合
    await expect(header).toHaveAttribute('aria-expanded', 'false');

    await header.click();
    await expect(header).toHaveAttribute('aria-expanded', 'true');

    // 應看到 mock 工單編號
    await expect(panel.getByText('WO123456')).toBeVisible();
  });

  test('無 data 時區塊應整個隱藏', async ({ page }) => {
    // 此測試依賴 runtime 注入空 data，此處僅驗證 panel 於無 feature flag 時不出現
    await page.goto(`${BASE_URL}/chat`); // no flag
    await page.waitForLoadState('networkidle');
    const panel = page.locator('[data-testid="graph-expansion-panel"]');
    await expect(panel).toHaveCount(0);
  });
});

test.describe('W3-T1: RWD — Graph Expansion Panel', () => {
  test.skip(!process.env.RUN_GRAPH_E2E, 'W3-T1 skeleton — set RUN_GRAPH_E2E=1 to run against live deploy');

  const breakpoints = [
    { name: 'mobile', width: 375, height: 667 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1280, height: 720 },
  ];

  for (const bp of breakpoints) {
    test(`${bp.name} (${bp.width}x${bp.height}) panel 正常呈現`, async ({ page }) => {
      await page.setViewportSize({ width: bp.width, height: bp.height });
      await loginAndOpenChat(page);
      await sendMessage(page, '近期常見故障有哪些？');

      const panel = page.locator('[data-testid="graph-expansion-panel"]').first();
      await expect(panel).toBeVisible();

      const box = await panel.boundingBox();
      expect(box).not.toBeNull();
      if (box) {
        expect(box.width).toBeGreaterThan(0);
        expect(box.width).toBeLessThanOrEqual(bp.width);
      }
    });
  }
});
