/**
 * AIKM Platform — Chat History Navigation Regression
 *
 * 迴歸測試：點擊側邊欄歷史對話後應正確切換並渲染對應訊息。
 * Bug 背景：backend INSERT :metadata::jsonb 失敗曾導致訊息存不進 DB，
 *   前端點進對話看到空白被誤判為「無法進入」。修復後新訊息可正常寫入，
 *   前端也會在既有但無訊息的對話顯示明確提示而非全新對話歡迎畫面。
 */

import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://192.168.1.11:3000';
const API_URL = process.env.API_URL || 'http://192.168.1.11:8000';
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin123';

async function loginAsAdmin(page: Page) {
  await page.goto(`${BASE_URL}/login`);
  if (page.url().includes('/login')) {
    await page.getByPlaceholder('請輸入您的電子郵件').fill(ADMIN_EMAIL);
    await page.getByPlaceholder('請輸入密碼').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: '登入' }).click();
  }
  await page.waitForURL(/\/chat/, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
}

test.describe('Chat History Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('click historical conversation sets active id and triggers GET /api/conversations/:id', async ({ page }) => {
    // 開啟歷史對話下拉
    const histBtn = page.locator('button').filter({ has: page.locator('svg') }).filter({ hasText: /^\d+$/ }).first();
    const hasHistory = await histBtn.isVisible({ timeout: 5000 }).catch(() => false);
    test.skip(!hasHistory, 'No history button visible');
    await histBtn.click();

    // 等待對話列表出現
    const item = page.locator('[data-testid="conversation-item"]').first();
    await expect(item).toBeVisible({ timeout: 5000 });

    const convId = await item.getAttribute('data-conversation-id');
    expect(convId).toBeTruthy();

    // 監聽 API 請求
    const respPromise = page.waitForResponse(
      (resp) => resp.url().includes(`/api/conversations/${convId}`) && resp.status() === 200,
      { timeout: 10000 }
    );

    await item.click();
    const resp = await respPromise;
    expect(resp.ok()).toBeTruthy();

    // 驗證 activeConversationId 有正確被設到 localStorage（user-scoped key）
    const activeId = await page.evaluate(() => {
      const key = Object.keys(localStorage).find((k) => k.startsWith('activeConversationId_'));
      return key ? localStorage.getItem(key) : null;
    });
    expect(activeId).toBe(convId);
  });

  test('entering empty historical conversation shows empty-state hint (not generic welcome)', async ({ page }) => {
    const histBtn = page.locator('button').filter({ hasText: /^\d+$/ }).first();
    const hasHistory = await histBtn.isVisible({ timeout: 5000 }).catch(() => false);
    test.skip(!hasHistory, 'No history button');
    await histBtn.click();

    const items = page.locator('[data-testid="conversation-item"]');
    const count = await items.count();
    test.skip(count === 0, 'No historical conversations');

    await items.first().click();
    await page.waitForTimeout(1500);

    // 應看到 empty-conversation-hint 或 message bubble，兩者至少一個
    const emptyHint = page.locator('[data-testid="empty-conversation-hint"]');
    const messages = page.locator('[data-testid="message"]');
    const hasEmpty = await emptyHint.isVisible().catch(() => false);
    const msgCount = await messages.count();

    expect(hasEmpty || msgCount > 0).toBeTruthy();

    // 若是空對話，確認不是 welcome-greeting（避免誤判為「沒選到對話」）
    if (hasEmpty) {
      const welcomeVisible = await page
        .locator('[data-testid="welcome-greeting"]')
        .isVisible()
        .catch(() => false);
      expect(welcomeVisible).toBeFalsy();
    }
  });

  test('conversation with messages renders bubbles after click', async ({ page, request }) => {
    // 先用 API 確保至少一個對話有訊息（寫入一條測試訊息）
    const loginRes = await request.post(`${API_URL}/api/auth/login`, {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const { token } = await loginRes.json();

    const listRes = await request.get(`${API_URL}/api/conversations?limit=5`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const convs = await listRes.json();
    test.skip(!convs?.length, 'No conversations');
    const targetConvId = convs[0].id;

    const probeMsgId = `e2e_probe_${Date.now()}`;
    await request.post(`${API_URL}/api/conversations/${targetConvId}/messages`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { id: probeMsgId, role: 'user', content: 'E2E probe message', metadata: {} },
    });

    try {
      // 重新整理讓 store 重新 sync
      await page.reload();
      await page.waitForLoadState('networkidle');

      // 開啟歷史對話下拉
      const histBtn = page.locator('button').filter({ hasText: /^\d+$/ }).first();
      await histBtn.click();

      // 點擊目標對話（靠 data-conversation-id）
      const target = page.locator(`[data-conversation-id="${targetConvId}"]`);
      await expect(target).toBeVisible({ timeout: 5000 });
      await target.click();

      // 等待訊息 render
      await expect(
        page.locator('[data-testid="message"]').filter({ hasText: 'E2E probe message' })
      ).toBeVisible({ timeout: 10000 });

      const msgCount = await page.locator('[data-testid="message"]').count();
      expect(msgCount).toBeGreaterThan(0);
    } finally {
      // 清理測試訊息（若後端無 DELETE endpoint 則忽略）
      await request
        .delete(`${API_URL}/api/conversations/${targetConvId}/messages/${probeMsgId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        .catch(() => {});
      // 測試訊息若殘留，會以 e2e_probe_ 前綴識別，可用 DB 定期清理
    }
  });
});
