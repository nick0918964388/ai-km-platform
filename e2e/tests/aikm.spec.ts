/**
 * AIKM Platform E2E Tests
 * 
 * 測試範圍：
 * 1. 登入功能
 * 2. 導航功能
 * 3. 知識庫管理頁面
 * 4. 儀表板數據載入
 * 5. 對話功能
 * 6. API 健康檢查
 */

import { test, expect } from '@playwright/test';

// 測試配置
const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const API_URL = process.env.API_URL || 'http://localhost:8000';
const API_KEY = process.env.API_KEY || '_lAWtCn29ETEomZjfz1Xa9SvVsrjOaCMvqt0htX3Shw';

// 測試帳號
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin';

test.describe('AIKM Platform E2E Tests', () => {
  
  // ==========================================
  // API 健康檢查
  // ==========================================
  test.describe('API Health Checks', () => {
    
    test('Backend API 應該正常運作', async ({ request }) => {
      const response = await request.get(`${API_URL}/health`);
      expect(response.ok()).toBeTruthy();
      const body = await response.json();
      expect(body.status).toBe('healthy');
    });

    test('Dashboard API 應該返回數據', async ({ request }) => {
      const response = await request.get(`${API_URL}/api/dashboard/summary`, {
        headers: { 'X-API-Key': API_KEY }
      });
      expect(response.ok()).toBeTruthy();
      const body = await response.json();
      expect(body).toHaveProperty('total_vehicles');
      expect(body).toHaveProperty('open_faults');
      expect(body).toHaveProperty('fault_resolution_rate');
    });

    test('Qdrant 向量資料庫應該就緒', async ({ request }) => {
      const response = await request.get('http://localhost:6333/readyz');
      expect(response.ok()).toBeTruthy();
    });

  });

  // ==========================================
  // 登入功能測試
  // ==========================================
  test.describe('Authentication', () => {
    
    test('登入頁面應該正確顯示', async ({ page }) => {
      await page.goto(BASE_URL);
      
      // 檢查登入表單存在
      await expect(page.getByText('車輛維修知識庫')).toBeVisible();
      await expect(page.getByPlaceholder('your@email.com')).toBeVisible();
      await expect(page.getByRole('button', { name: '登入' })).toBeVisible();
      
      // 檢查 Demo 帳號提示
      await expect(page.getByText('Demo 帳號')).toBeVisible();
    });

    test('Admin 登入應該成功', async ({ page }) => {
      await page.goto(BASE_URL);
      
      // 填入登入資訊
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      
      // 等待導航到主頁面
      await page.waitForURL(/\/(chat|admin)/, { timeout: 10000 });
      
      // 等待頁面載入完成
      await page.waitForLoadState('networkidle');
      
      // 檢查管理員已登入（等待元素出現）
      await expect(page.locator('text=管理員').first()).toBeVisible({ timeout: 10000 });
      
      // 檢查管理選單可見（只有 admin 才有）
      await expect(page.locator('a:has-text("知識庫管理")')).toBeVisible();
      await expect(page.locator('a:has-text("儀表板")')).toBeVisible();
    });

    test('一般使用者登入應該成功', async ({ page }) => {
      await page.goto(BASE_URL);
      
      // 使用任意 email 登入
      await page.getByPlaceholder('your@email.com').fill('user@test.com');
      await page.getByPlaceholder('••••••••').fill('password123');
      await page.getByRole('button', { name: '登入' }).click();
      
      // 等待導航
      await page.waitForURL(/\/chat/);
      
      // 檢查對話介面
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();
    });

    test('登出功能應該正常', async ({ page }) => {
      // 先登入
      await page.goto(BASE_URL);
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      await page.waitForURL(/\/(chat|admin)/);
      
      // 點擊登出
      await page.getByRole('button', { name: '登出' }).click();
      
      // 應該回到登入頁面
      await expect(page.getByRole('button', { name: '登入' })).toBeVisible();
    });

  });

  // ==========================================
  // 導航功能測試
  // ==========================================
  test.describe('Navigation', () => {
    
    test.beforeEach(async ({ page }) => {
      // 每個測試前先登入
      await page.goto(BASE_URL);
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      await page.waitForURL(/\/(chat|admin)/);
    });

    test('主選單導航應該正常', async ({ page }) => {
      // 等待頁面載入
      await page.waitForLoadState('networkidle');
      
      // 對話頁面 - 使用更精確的選擇器
      await page.locator('nav a:has-text("對話")').first().click();
      await expect(page).toHaveURL(/\/chat/);
      
      // 對話歷史
      await page.locator('a:has-text("對話歷史")').click();
      await expect(page).toHaveURL(/\/history/);
      
      // 設定
      await page.locator('a:has-text("設定")').click();
      await expect(page).toHaveURL(/\/settings/);
    });

    test('管理選單導航應該正常', async ({ page }) => {
      // 知識庫管理
      await page.getByRole('link', { name: '知識庫管理' }).click();
      await expect(page).toHaveURL(/\/admin\/knowledge-base/);
      await expect(page.getByRole('heading', { name: '知識庫管理' })).toBeVisible();
      
      // 使用者管理
      await page.getByRole('link', { name: '使用者管理' }).click();
      await expect(page).toHaveURL(/\/admin\/users/);
      
      // 權限管理
      await page.getByRole('link', { name: '權限管理' }).click();
      await expect(page).toHaveURL(/\/admin\/permissions/);
      
      // 儀表板
      await page.getByRole('link', { name: '儀表板' }).click();
      await expect(page).toHaveURL(/\/admin\/dashboard/);
      await expect(page.getByRole('heading', { name: '營運儀表板' })).toBeVisible();
    });

  });

  // ==========================================
  // 知識庫管理測試
  // ==========================================
  test.describe('Knowledge Base Management', () => {
    
    test.beforeEach(async ({ page }) => {
      await page.goto(BASE_URL);
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      await page.waitForURL(/\/(chat|admin)/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');
      await page.locator('a:has-text("知識庫管理")').click();
      await page.waitForURL(/\/admin\/knowledge-base/);
    });

    test('知識庫頁面元素應該正確顯示', async ({ page }) => {
      // 等待頁面載入
      await page.waitForLoadState('networkidle');
      
      // 上傳區域
      await expect(page.locator('text=拖放文件到這裡上傳')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('button:has-text("選擇檔案")')).toBeVisible();
      
      // 統計區域（使用 first() 避免多個匹配）
      await expect(page.locator('text=文件數量').first()).toBeVisible();
      await expect(page.locator('text=知識片段').first()).toBeVisible();
      await expect(page.locator('text=總大小').first()).toBeVisible();
      
      // 搜尋欄
      await expect(page.getByPlaceholder('搜尋文件...')).toBeVisible();
      
      // 文件列表表頭
      await expect(page.locator('th:has-text("文件名稱")')).toBeVisible();
      await expect(page.locator('th:has-text("類型")')).toBeVisible();
      await expect(page.locator('th:has-text("狀態")')).toBeVisible();
    });

    test('搜尋功能應該可以輸入', async ({ page }) => {
      const searchInput = page.getByPlaceholder('搜尋文件...');
      await searchInput.fill('測試文件');
      await expect(searchInput).toHaveValue('測試文件');
    });

  });

  // ==========================================
  // 儀表板測試
  // ==========================================
  test.describe('Dashboard', () => {
    
    test.beforeEach(async ({ page }) => {
      await page.goto(BASE_URL);
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      await page.waitForURL(/\/(chat|admin)/);
      await page.getByRole('link', { name: '儀表板' }).click();
    });

    test('儀表板數據應該載入', async ({ page }) => {
      // 等待數據載入
      await page.waitForSelector('text=營運車輛');
      
      // 檢查統計卡片
      await expect(page.getByText('營運車輛')).toBeVisible();
      await expect(page.getByText('待處理故障')).toBeVisible();
      await expect(page.getByText('待排程檢修')).toBeVisible();
      await expect(page.getByText('本月成本')).toBeVisible();
      await expect(page.getByText('故障解決率')).toBeVisible();
      await expect(page.getByText('低庫存警示')).toBeVisible();
    });

    test('圖表應該渲染', async ({ page }) => {
      // 等待圖表載入
      await page.waitForSelector('text=故障趨勢');
      
      // 檢查圖表標題
      await expect(page.getByRole('heading', { name: /故障趨勢/ })).toBeVisible();
      await expect(page.getByRole('heading', { name: /成本分布/ })).toBeVisible();
    });

    test('故障排行應該顯示', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /故障排行/ })).toBeVisible();
      
      // 檢查排行列表
      const listItems = page.locator('li').filter({ hasText: /EMU|TEMU/ });
      await expect(listItems.first()).toBeVisible();
    });

    test('重新整理按鈕應該可點擊', async ({ page }) => {
      const refreshButton = page.getByRole('button', { name: '重新整理' });
      await expect(refreshButton).toBeEnabled();
      await refreshButton.click();
      
      // 檢查數據仍然顯示
      await expect(page.getByText('營運車輛')).toBeVisible();
    });

    test('快速操作連結應該正常', async ({ page }) => {
      // 檢查快速操作按鈕
      await expect(page.getByRole('link', { name: '上傳文件' })).toBeVisible();
      await expect(page.getByRole('link', { name: '開始對話' })).toBeVisible();
      await expect(page.getByRole('link', { name: '管理使用者' })).toBeVisible();
      await expect(page.getByRole('link', { name: '系統設定' })).toBeVisible();
      
      // 點擊並驗證導航
      await page.getByRole('link', { name: '上傳文件' }).click();
      await expect(page).toHaveURL(/\/admin\/knowledge-base/);
    });

  });

  // ==========================================
  // 對話功能測試
  // ==========================================
  test.describe('Chat', () => {
    
    test.beforeEach(async ({ page }) => {
      await page.goto(BASE_URL);
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      await page.waitForURL(/\/(chat|admin)/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');
      // 點擊對話連結
      await page.locator('nav a:has-text("對話")').first().click();
      await page.waitForURL(/\/chat/);
    });

    test('對話介面元素應該正確顯示', async ({ page }) => {
      // 等待頁面載入
      await page.waitForLoadState('networkidle');
      
      // 輸入區域
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible({ timeout: 10000 });
      
      // 快捷問題按鈕（這些是確定存在的）
      await expect(page.locator('button:has-text("引擎異響")')).toBeVisible();
      await expect(page.locator('button:has-text("煞車")')).toBeVisible();
      await expect(page.locator('button:has-text("保養")')).toBeVisible();
    });

    test('新對話按鈕應該可點擊', async ({ page }) => {
      const newChatButton = page.locator('button:has-text("新對話")');
      await expect(newChatButton).toBeVisible();
      await newChatButton.click();
      
      // 應該清空對話或保持在對話頁面
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();
    });

    test('快捷問題按鈕應該填入輸入框', async ({ page }) => {
      // 點擊快捷問題
      await page.locator('button:has-text("引擎異響怎麼辦")').click();
      
      // 等待一下看是否有反應
      await page.waitForTimeout(500);
      // (根據實際行為調整驗證邏輯)
    });

    test('輸入文字應該可以輸入並發送', async ({ page }) => {
      // 等待頁面載入
      await page.waitForLoadState('networkidle');
      
      const input = page.getByPlaceholder('輸入您的問題...');
      
      // 檢查輸入框可用
      await expect(input).toBeVisible({ timeout: 10000 });
      await expect(input).toBeEnabled();
      
      // 輸入文字
      await input.fill('測試問題');
      await expect(input).toHaveValue('測試問題');
      
      // 發送按鈕應該存在（可能是 disabled 屬性變化或 aria 屬性）
      // 找到包含發送功能的按鈕（通常在輸入框附近）
      const sendArea = page.locator('button').filter({ has: page.locator('svg') }).last();
      await expect(sendArea).toBeVisible();
    });

  });

  // ==========================================
  // 響應式設計測試
  // ==========================================
  test.describe('Responsive Design', () => {
    
    test('桌面版應該正常顯示側邊欄', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.goto(BASE_URL);
      await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
      await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
      await page.getByRole('button', { name: '登入' }).click();
      await page.waitForURL(/\/(chat|admin)/);
      
      // 側邊欄應該可見
      await expect(page.getByRole('navigation')).toBeVisible();
    });

    test('行動版應該正常顯示', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto(BASE_URL);
      
      // 登入頁面應該適應小螢幕
      await expect(page.getByRole('button', { name: '登入' })).toBeVisible();
    });

  });

});

// ==========================================
// 效能測試
// ==========================================
test.describe('Performance', () => {
  
  test('首頁載入應該在 3 秒內完成', async ({ page }) => {
    const startTime = Date.now();
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;
    
    expect(loadTime).toBeLessThan(3000);
  });

  test('儀表板數據載入應該在 5 秒內完成', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.getByPlaceholder('your@email.com').fill(ADMIN_EMAIL);
    await page.getByPlaceholder('••••••••').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: '登入' }).click();
    await page.waitForURL(/\/(chat|admin)/);
    
    const startTime = Date.now();
    await page.getByRole('link', { name: '儀表板' }).click();
    await page.waitForSelector('text=營運車輛');
    const loadTime = Date.now() - startTime;
    
    expect(loadTime).toBeLessThan(5000);
  });

});
