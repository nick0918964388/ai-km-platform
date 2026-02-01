# AI KM Platform - 車輛維修知識管理系統

## 專案概述
AI 驅動的車輛維修知識管理平台，提供類似 Gemini 的對話介面。

## 功能需求

### Phase 1 - 前端 (目前)
- [ ] 對話介面
  - [ ] 文字輸入
  - [ ] 語音輸入 (Web Speech API)
  - [ ] 圖片上傳
- [ ] 使用者系統
  - [ ] 登入/登出
  - [ ] 權限管理 (Admin/User/Guest)
  - [ ] 帳號管理 (CRUD)
- [ ] 系統管理
  - [ ] 全域設定
  - [ ] 主題設定

### Phase 2 - 後端 (待開發)
- [ ] 車輛維修知識庫 API
- [ ] RAG 系統整合
- [ ] 向量資料庫

## 技術棧
- **Frontend:** Next.js 14, TypeScript, IBM Carbon Design
- **Auth:** NextAuth.js
- **State:** Zustand
- **Style:** Carbon Design System (Blue Theme)

## 設計原則
- IBM Carbon Design 風格
- 藍色主題 (#0f62fe)
- 簡約設計，減少顏色
