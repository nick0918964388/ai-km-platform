# AIKM Platform E2E Tests

使用 Playwright 進行端對端測試。

## 快速開始

### 1. 安裝依賴

```bash
cd e2e
npm install
npx playwright install
```

### 2. 確保服務運行

確保以下服務已啟動：
- Docker 服務：`docker compose up -d postgres qdrant redis`
- Backend：`http://localhost:8000`
- Frontend：`http://localhost:3000`

### 3. 執行測試

```bash
# 執行所有測試
npm test

# 帶 UI 介面執行
npm run test:ui

# 只測試 Chrome
npm run test:chromium

# 開啟瀏覽器執行（看到過程）
npm run test:headed

# Debug 模式
npm run test:debug
```

## 測試覆蓋範圍

### API 健康檢查
- ✅ Backend API 健康狀態
- ✅ Dashboard API 數據返回
- ✅ Qdrant 向量資料庫就緒

### 認證功能
- ✅ 登入頁面顯示
- ✅ Admin 登入
- ✅ 一般使用者登入
- ✅ 登出功能

### 導航功能
- ✅ 主選單導航
- ✅ 管理選單導航

### 知識庫管理
- ✅ 頁面元素顯示
- ✅ 搜尋功能

### 儀表板
- ✅ 統計數據載入
- ✅ 圖表渲染
- ✅ 故障排行顯示
- ✅ 重新整理功能
- ✅ 快速操作連結

### 對話功能
- ✅ 介面元素顯示
- ✅ 新對話功能
- ✅ 快捷問題
- ✅ 發送按鈕狀態

### 響應式設計
- ✅ 桌面版顯示
- ✅ 行動版顯示

### 效能測試
- ✅ 首頁載入時間
- ✅ 儀表板載入時間

## 查看報告

測試完成後，執行以下命令查看 HTML 報告：

```bash
npm run report
```

報告會自動在瀏覽器中開啟。

## 錄製新測試

使用 Playwright Codegen 錄製操作：

```bash
npm run codegen
```

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| BASE_URL | http://localhost:3000 | 前端 URL |
| API_URL | http://localhost:8000 | 後端 API URL |
| CI | - | CI 環境標記 |

## 目錄結構

```
e2e/
├── tests/
│   └── aikm.spec.ts     # 主要測試檔案
├── playwright.config.ts # Playwright 配置
├── package.json
└── README.md
```

## 新增測試

在 `tests/` 目錄下新增 `.spec.ts` 檔案，Playwright 會自動偵測並執行。

範例：

```typescript
import { test, expect } from '@playwright/test';

test('我的新測試', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await expect(page).toHaveTitle(/AIKM/);
});
```
