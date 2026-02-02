# 設計系統更新摘要

**更新日期**: 2026-02-02

## 變更概述

本次更新根據 Pencil MCP 設計稿，將 AIKM 平台的設計系統從原有配色方案更新為更現代化的藍色主題。

## 主要變更

### 1. 色彩系統 (Color Palette)

| 角色 | 舊值 | 新值 | 說明 |
|------|------|------|------|
| Primary | `#003366` | `#2563EB` | 從深藍色改為更明亮的藍色 |
| Primary Light | `#E8F0F8` | `#EFF6FF` | 選中/Hover 狀態背景色 |
| Text Primary | `#1E293B` | `#18181B` | 主要文字顏色（更深） |
| Text Secondary | `#64748B` | `#71717A` | 次要文字顏色 |
| Text Muted | `#94A3B8` | `#666666` | 淡化文字顏色 |
| Border | `#E2E8F0` | `#E4E4E7` | 主要邊框顏色 |
| Border Light | `#F1F5F9` | `#E5E5E5` | 淺邊框顏色 |
| Background Alt | `#F8FAFC` | `#F8FAFC` | 保持不變 |
| Background Tertiary | `#F1F5F9` | `#FAFAFA` | 極淺灰背景 |

### 2. 圓角尺寸 (Border Radius)

| 尺寸 | 舊值 | 新值 | 使用場景 |
|------|------|------|----------|
| Small | `4px` | `8px` | 導航項目 |
| Medium | `6px` | `10px` | Logo、小按鈕 |
| Large | `8px` | `12px` | 輸入框、按鈕 |
| XLarge | `12px` | `16px` | 卡片、Modal |

### 3. 邊框厚度 (Border Width)

- 關鍵組件邊框從 `1px` 更新為 `1.5px`，提供更清晰的視覺分隔
- 影響組件：卡片、輸入框、表格、搜索框、Chat 輸入框

### 4. 組件更新

#### 已更新的全域樣式類 (globals.css)
- `.card` - 邊框 1.5px，圓角 16px
- `.stat-card` - 邊框 1.5px，圓角 16px
- `.form-input` - 邊框 1.5px，圓角 12px
- `.table-container` - 邊框 1.5px
- `.login-card` - 邊框 1.5px
- `.search-box` - 邊框 1.5px，圓角 12px
- `.chat-input-wrapper` - 邊框 1.5px

## 設計原則

設計系統遵循以下原則：

1. **簡約設計 (Minimalist Design)** - 去除不必要的裝飾
2. **高對比度** - 確保文字可讀性
3. **充足留白** - 讓內容有呼吸空間
4. **扁平化設計** - 無立體感或擬真效果
5. **極輕微陰影** - 或完全無陰影
6. **純色背景** - 無漸層或模糊效果

## 組件使用 CSS 變數

所有前端組件均正確使用 CSS 變數，無硬編碼顏色：

### 推薦使用方式

```tsx
// ✅ 正確 - 使用 CSS 變數
<div style={{ color: 'var(--text-primary)' }}>文字</div>
<div style={{ background: 'var(--primary)' }}>按鈕</div>

// ❌ 錯誤 - 硬編碼顏色
<div style={{ color: '#18181B' }}>文字</div>
<div style={{ background: '#2563EB' }}>按鈕</div>
```

### 可用的 CSS 變數

```css
/* 背景 */
var(--bg-primary)      /* #FFFFFF - 主要背景 */
var(--bg-secondary)    /* #F8FAFC - 次要背景 */
var(--bg-tertiary)     /* #FAFAFA - 極淺灰背景 */
var(--bg-card)         /* #FFFFFF - 卡片背景 */

/* 文字 */
var(--text-primary)    /* #18181B - 主要文字 */
var(--text-secondary)  /* #71717A - 次要文字 */
var(--text-muted)      /* #666666 - 淡化文字 */

/* 邊框 */
var(--border)          /* #E4E4E7 - 標準邊框 */
var(--border-light)    /* #E5E5E5 - 淺色邊框 */

/* 主題色 */
var(--primary)         /* #2563EB - 主要藍色 */
var(--primary-light)   /* #EFF6FF - 淺藍背景 */

/* 圓角 */
var(--radius-sm)       /* 8px */
var(--radius-md)       /* 10px */
var(--radius-lg)       /* 12px */
var(--radius-xl)       /* 16px */

/* 陰影 */
var(--shadow-sm)       /* 極輕微陰影 */
var(--shadow-md)       /* 中等陰影 */
```

## 佈局尺寸

從 Pencil 設計稿提取的標準尺寸：

- **側邊欄寬度**: 260px
- **Header 高度**: 64px - 72px
- **輸入框高度**: 40px - 56px
- **按鈕高度**: 40px - 52px
- **導航項目高度**: 44px

## 排版規範

- **字體家族**: Inter (主要字體)
- **字重**:
  - 400 (normal) - 一般文字
  - 500 (medium) - 小標籤文字
  - 600 (semibold) - 次要標題
  - 700 (bold) - 主標題
- **字體大小**:
  - 11px - 導航標籤 (letterSpacing: 1px)
  - 14px - 一般文字
  - 16px - 描述文字
  - 18px - 品牌名稱
  - 24px - 頁面標題
  - 32px - 大標題

## 驗證清單

- [x] 更新 DESIGN_SYSTEM.md 文件
- [x] 更新 globals.css CSS 變數
- [x] 更新所有組件邊框厚度為 1.5px
- [x] 更新圓角尺寸
- [x] 驗證無硬編碼顏色
- [x] 確保組件使用 CSS 變數

## 向後兼容性

由於所有組件都使用 CSS 變數，此次更新僅需修改 `globals.css`，無需逐一修改組件文件。這確保了：

1. **集中管理** - 所有顏色在一個文件中定義
2. **易於維護** - 未來變更只需修改 CSS 變數
3. **無破壞性** - 不影響現有組件邏輯
4. **主題支持** - 為未來的深色模式或其他主題打下基礎

## 下一步

1. 在開發環境中測試所有頁面和組件
2. 驗證不同螢幕尺寸的響應式設計
3. 確認無障礙性 (Accessibility) 標準
4. 收集用戶反饋並進行必要調整

## 相關文件

- `DESIGN_SYSTEM.md` - 完整的設計系統規範
- `frontend/src/app/globals.css` - CSS 變數定義
- Pencil 設計稿: `/Users/nickall/Downloads/aikm`
