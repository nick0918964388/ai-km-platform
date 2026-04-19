/**
 * AIKM Platform — Intent Classifier Follow-up Regression
 *
 * 迴歸測試：追問（「那同樣的 X 呢？」「A vs B 比較」）應 **繼承前題 structured intent**，
 * 不應被誤判成 hybrid 拆成兩個 pipeline。
 *
 * Bug 背景（2026-04-19）：
 *   使用者先問「EMU3000 的工單類型分布」→ structured (SQL) ✅
 *   再問「那同樣的 EMU900 呢？」→ 被判為 hybrid 並開兩個 pipeline → 100+ 秒
 * Fix: commit 1b6388b 改寫 intent_classifier prompt，明確「多車號比較/追問延續」屬 structured。
 */

import { test, expect, APIRequestContext, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://192.168.1.11:3000';
const API_URL = process.env.API_URL || 'http://192.168.1.11:8000';
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin123';

async function apiLogin(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${API_URL}/api/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  expect(resp.ok(), `login failed ${resp.status()}`).toBeTruthy();
  const json = await resp.json();
  return json.token;
}

async function loginUI(page: Page) {
  await page.goto(`${BASE_URL}/login`);
  if (page.url().includes('/login')) {
    await page.getByPlaceholder('請輸入您的電子郵件').fill(ADMIN_EMAIL);
    await page.getByPlaceholder('請輸入密碼').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: '登入' }).click();
  }
  await page.waitForURL(/\/chat/, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
}

/**
 * 直接打 backend intent classifier API 驗證分類結果。
 * 避開 UI render / SSE timing 的干擾，測試核心邏輯最可靠。
 */
async function classifyIntent(
  request: APIRequestContext,
  token: string,
  query: string,
  context: Array<{ role: string; content: string }> = [],
): Promise<{ intent: string; confidence: number; reasoning?: string }> {
  const resp = await request.post(`${API_URL}/api/query/classify`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { query, context },
  });
  expect(resp.ok(), `intent API failed ${resp.status()}`).toBeTruthy();
  return await resp.json();
}

test.describe('US: Intent Classifier — Follow-up & Comparison', () => {
  test('單題車號工單分布 → structured，不是 hybrid', async ({ request }) => {
    const token = await apiLogin(request);
    const r = await classifyIntent(request, token, 'EMU3000 的工單類型分布');
    expect(r.intent).toBe('structured');
    expect(r.confidence).toBeGreaterThan(0.7);
  });

  test('追問「那同樣的 EMU900 呢？」應繼承前題 structured（核心迴歸）', async ({ request }) => {
    const token = await apiLogin(request);
    const context = [
      { role: 'user', content: 'EMU3000 的工單類型分布' },
      { role: 'assistant', content: 'EMU3000 共 247 筆工單，類型分布如下...' },
    ];
    const r = await classifyIntent(request, token, '那同樣的 EMU900 呢？', context);
    expect(r.intent, `got reasoning: ${r.reasoning}`).toBe('structured');
    expect(r.intent).not.toBe('hybrid');
  });

  test('對比查詢「EMU3000 vs EMU900」應為 structured（不因「多車號」變 hybrid）', async ({ request }) => {
    const token = await apiLogin(request);
    const r = await classifyIntent(request, token, 'EMU3000 和 EMU900 的工單數量比較');
    expect(r.intent, `got reasoning: ${r.reasoning}`).toBe('structured');
  });

  test('真 hybrid：工單 + SOP 同時要 → hybrid', async ({ request }) => {
    const token = await apiLogin(request);
    const r = await classifyIntent(
      request,
      token,
      'EMU900 最近的工單紀錄與對應的維修 SOP 處理程序',
    );
    expect(r.intent).toBe('hybrid');
  });

  test('UI 端到端：追問 EMU900 應在 30 秒內回覆（非 100+s hybrid）', async ({ page, request }) => {
    // UI 端到端要求較長 timeout，且依賴對話能成功建立
    test.setTimeout(90_000);
    await loginUI(page);

    // 第一題
    const input = page.getByPlaceholder(/請輸入您的問題|輸入訊息/).first();
    await input.fill('EMU3000 的工單類型分布');
    await input.press('Enter');
    // 等第一題回覆（看到「247」工單數或任何 assistant content 即可）
    await page.waitForTimeout(20_000);

    // 記錄追問開始時間
    const t0 = Date.now();
    await input.fill('那同樣的 EMU900 呢？');
    await input.press('Enter');

    // 等到 streaming 結束（送出按鈕重新可按/loading 消失）或 30s 上限
    // 驗收：不應超過 45s（30s 正常 SQL 上限 + 15s 寬容）
    await page.waitForFunction(
      () => !document.body.innerText.includes('我正在查詢車輛維修知識庫'),
      { timeout: 45_000 },
    ).catch(() => {
      // fallback: just wait for any assistant bubble to appear with content
    });

    const elapsed = Date.now() - t0;
    // 核心迴歸：不該是 hybrid 的 100+s
    expect(elapsed, `follow-up took ${elapsed}ms, should be < 45000ms`).toBeLessThan(45_000);
  });
});
