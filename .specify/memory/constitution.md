<!--
Sync Impact Report
==================
Version change: N/A → 1.0.0 (Initial ratification)
Modified principles: N/A (new constitution)
Added sections:
  - Core Principles (5 principles)
  - Technical Standards
  - Development Workflow
  - Governance
Removed sections: N/A
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ (compatible - uses generic Constitution Check)
  - .specify/templates/spec-template.md ✅ (compatible - no principle-specific references)
  - .specify/templates/tasks-template.md ✅ (compatible - no principle-specific references)
Follow-up TODOs: None
-->

# AI 知識管理平台 Constitution

## Core Principles

### I. 程式碼品質 (Code Quality)

所有程式碼 MUST 遵循以下標準：

- **Python**: 使用 Python 3.10+ 版本，MUST 遵循 PEP 8 風格指南
- **TypeScript**: 前端程式碼 MUST 使用 TypeScript，啟用 strict mode
- **型別標註**: 所有函數 MUST 包含完整的型別標註 (type hints/annotations)
- **程式碼審查**: 所有變更 MUST 經過 code review 才能合併

**Rationale**: 統一的程式碼標準確保團隊協作效率，型別安全降低執行期錯誤風險。

### II. 效能優先 (Performance First)

系統效能 MUST 符合以下基準：

- **RAG 搜尋回應**: 端到端回應時間 MUST < 2 秒 (p95)
- **向量搜尋**: 單次向量檢索 MUST < 500ms
- **API 回應**: 一般 API 端點 MUST < 200ms (p95)
- **效能監控**: 所有關鍵路徑 MUST 包含效能量測與日誌

**Rationale**: 知識管理系統的使用者體驗取決於即時回應能力，延遲會直接影響生產力。

### III. 可維護性 (Maintainability)

架構設計 MUST 遵循以下原則：

- **模組化設計**: 功能 MUST 以獨立模組實作，避免緊耦合
- **服務層分離**: 業務邏輯 MUST 與資料存取、API 層分離
- **依賴注入**: 服務間依賴 SHOULD 透過依賴注入實現，便於測試與替換
- **文件同步**: API 變更 MUST 同步更新相關文件

**Rationale**: 清晰的架構邊界降低維護成本，支援團隊獨立開發與部署。

### IV. 中文優先 (Chinese-First)

系統 MUST 優先支援繁體中文：

- **術語庫**: MUST 建立並維護台鐵專業術語庫（如 EMU800 維修文件術語）
- **分詞處理**: 中文文件處理 MUST 使用適當的中文分詞工具
- **Embedding 模型**: MUST 選用支援中文的 embedding 模型
- **UI/UX**: 使用者介面 MUST 以繁體中文為主要語言

**Rationale**: 目標使用者為台鐵維修人員，系統需準確理解並處理專業中文術語。

### V. 安全性 (Security)

所有安全措施 MUST 符合以下要求：

- **API 認證**: 所有 API 端點 MUST 實作認證機制
- **敏感資料保護**: 密碼與 API 金鑰 MUST 使用環境變數或加密儲存
- **輸入驗證**: 所有使用者輸入 MUST 經過驗證與清理
- **日誌安全**: 日誌 MUST NOT 包含敏感資訊（密碼、token 等）

**Rationale**: 知識管理系統可能包含機密維修資訊，需確保資料安全與存取控制。

## Technical Standards

### 技術棧規範

| 層級 | 技術 | 版本要求 |
|------|------|----------|
| Backend | Python + FastAPI | Python 3.10+ |
| Frontend | Next.js + TypeScript | TypeScript strict mode |
| Vector DB | ChromaDB / Qdrant | 依部署環境選用 |
| Embedding | 支援中文的模型 | e.g., text2vec-chinese |
| LLM | OpenAI API / 本地模型 | 可配置切換 |

### 測試要求

- **單元測試**: 核心業務邏輯 MUST 有單元測試覆蓋
- **整合測試**: API 端點 MUST 有整合測試
- **效能測試**: 關鍵路徑 SHOULD 有效能基準測試

## Development Workflow

### 分支策略

- `main`: 穩定版本，MUST 通過所有測試
- `feature/*`: 功能開發分支
- `fix/*`: 錯誤修復分支

### 程式碼提交

- Commit 訊息 MUST 清楚描述變更內容
- 每個 commit SHOULD 專注於單一變更
- 合併前 MUST 通過 CI 檢查

### 審查流程

- 所有程式碼變更 MUST 建立 Pull Request
- PR MUST 至少有一位審查者核准
- 審查者 MUST 檢查 Constitution 合規性

## Governance

### 憲法效力

本 Constitution 為專案最高指導原則，所有開發決策 MUST 符合本文件規範。
當既有實作與 Constitution 衝突時，MUST 優先修正實作。

### 修訂程序

1. 提出修訂 PR 並說明修訂理由
2. 團隊討論並達成共識
3. 更新版本號（依語意版本規則）
4. 記錄修訂歷史

### 版本規則

- **MAJOR**: 移除或重新定義核心原則（不向後相容）
- **MINOR**: 新增原則或顯著擴展指導方針
- **PATCH**: 澄清、措辭修正、非語意性調整

### 合規檢查

- 每個 PR 審查 MUST 包含 Constitution 合規驗證
- 複雜度增加 MUST 提供正當理由
- 參考 `.specify/` 目錄下的模板進行開發規劃

**Version**: 1.0.0 | **Ratified**: 2026-01-31 | **Last Amended**: 2026-01-31
