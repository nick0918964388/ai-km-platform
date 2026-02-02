import { defineConfig, devices } from '@playwright/test';

/**
 * AIKM Platform Playwright Configuration
 * 
 * 執行方式：
 * - 全部測試：npx playwright test
 * - 有 UI：npx playwright test --ui
 * - 指定瀏覽器：npx playwright test --project=chromium
 * - 生成報告：npx playwright show-report
 */

export default defineConfig({
  testDir: './tests',
  
  /* 測試執行設定 */
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  
  /* 報告設定 */
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],
  
  /* 全域設定 */
  use: {
    /* Base URL */
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    
    /* 截圖設定 */
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
    
    /* 超時設定 */
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  /* 專案配置（瀏覽器） */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    /* 行動裝置測試 */
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],

  /* 本地開發時自動啟動服務 */
  webServer: [
    {
      command: 'cd ../backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      command: 'cd ../frontend && npm run dev',
      url: 'http://localhost:3000',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],

  /* 超時設定 */
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
});
