# ai-km-platform — Claude 工作手冊

> 三層記憶架構：CLAUDE.md（固定概要）→ memory/MEMORY.md（近期摘要）→ memory/daily/[日期].md（每日開發日誌）

---

## 專案概要

**AI Knowledge Management Platform** — 企業級 AI 知識管理平台。  
結合 RAG 技術，支援智慧文件問答、多模態輸入、結構化資料查詢（車輛維修管理場景）。

### 主要功能模組
| 模組 | 說明 |
|------|------|
| Chat / RAG | 文件問答，支援串流 SSE，來源引用 |
| 知識庫管理 | PDF/Word/Excel/圖片上傳、刪除、備份 |
| 結構化查詢 | NL→SQL，查詢車輛、故障、維修紀錄 |
| Dashboard | 統計圖表（Recharts），故障趨勢、費用分布 |
| Admin 後台 | 使用者、權限、知識庫、分析管理 |
| 個人資料 | Profile 頁、頭像上傳、查詢歷史 |

### 技術棧
| 層 | 技術 |
|----|------|
| Backend | Python 3.10+, FastAPI, Qdrant, PostgreSQL, Redis |
| LLM / Reranker | OpenAI GPT-4o, Cohere Reranker, BGE Sentence Transformers |
| Frontend | Next.js 15.5, React 19, IBM Carbon v1.100, Tailwind CSS v4 |
| 狀態 / 圖表 | Zustand, NextAuth, Recharts |
| 儲存 | `./storage/documents/`（文件），`./storage/avatars/`（頭像） |

---

## 部署環境

> ⚠️ **重要：Mac Mini 是開發機（寫 code 用），192.168.1.11 Ubuntu 是部署機（所有服務都跑在那邊）**

| 項目 | 值 |
|------|----|
| **部署主機** | **192.168.1.11（Ubuntu）** |
| API URL | `http://192.168.1.11:8000` |
| Frontend | `http://192.168.1.11:3000` |
| 開發機 | Mac Mini（只寫 code，不跑服務） |
| 遷移日期 | 2026-04-09（從 Mac Mini 遷移至 Ubuntu） |

**192.168.1.11 上同時運行**：Drone CI (8090)、Maximo Liberty (9080/9443)，停止 aikm 服務時勿影響這些服務。

### Docker 服務清單（全部在 192.168.1.11 上）
| 服務 | Container | Port |
|------|-----------|------|
| Frontend | aikm-frontend | 3000 |
| Backend | aikm-backend | 8000 |
| PostgreSQL | aikm-postgres | 5432 |
| Redis | aikm-redis | 6379 |
| Qdrant | aikm-qdrant | 6333/6334 |
| Maximo Extractor | aikm-maximo-extractor | 8080 |

---

## ⚠️ 強制規則

1. **部署一律在 192.168.1.11（Ubuntu）上執行**
   - ❌ 禁止：在 Mac Mini 本機執行 `docker compose up`、`docker exec` 操作生產資料庫
   - ✅ 正確：SSH 進 192.168.1.11 執行，或透過 Drone CI 部署

2. **DOCKER ONLY** — 所有服務必須透過 Docker Compose 運行
   - ❌ 禁止：`npm run dev`、`uvicorn`、`python main.py`（在 host 執行）
   - ✅ 允許：`docker compose up -d`

3. **後端異動必須重建容器**
   - `docker compose up -d --build backend`

### 常用 Docker 指令（在 192.168.1.11 上執行）
```bash
# SSH 進入部署機
ssh user@192.168.1.11

docker compose up -d                        # 啟動全部
docker compose up -d --build backend        # 重建後端
docker compose up -d --build frontend       # 重建前端
docker compose logs -f [service_name]       # 看 logs
docker compose down                         # 停止全部

# DB Migration（在部署機上執行）
docker exec -i aikm-postgres psql -U aikm -d aikm < backend/scripts/migration.sql
```

---

## 開發流程（Agent Team）

所有功能開發必須使用 **Agent Team** 模式，包含以下角色：

### 開發流程
1. **規劃** — 先分析需求，規劃架構與實作方案
2. **實作** — 用 Agent Team 平行開發（Backend + Frontend 可同時進行）
3. **Review** — 啟動 Review Agent 檢查安全性、正確性、架構問題
4. **測試** — 用 Playwright MCP 進行視覺驗證 + API 端點測試
5. **修正** — 根據 Review/Test 結果修正問題
6. **部署** — SSH 到 192.168.1.11 執行 `git pull` + `docker compose up -d --build`

### Agent 角色
| 角色 | 用途 | 說明 |
|------|------|------|
| **Implementation Agent** | 實作功能 | Backend/Frontend 分開派發，可平行 |
| **Review Agent** | 程式碼審查 | 檢查安全漏洞、SQL injection、權限問題、import 錯誤 |
| **Test Agent** | 測試驗證 | 用 Playwright MCP 截圖驗證 + curl API 測試 |

### 規範
- 實作完成後 **必須** 啟動 Review Agent（可在背景執行）
- Review 發現的 HIGH/CRITICAL 問題 **必須** 修正後才能交付
- 前端改動 **必須** 用 Playwright 截圖驗證
- 每次部署後 **必須** 確認 health check 通過
- Commit 後 **必須** push + 在 192.168.1.11 部署

---

## 我的偏好

- 回應語言：繁體中文
- 回應風格：簡潔直接，不加過多說明
- 不加無意義的結尾總結（我看得到 diff）
- **前端功能改動後，必須自動調用瀏覽器工具（Playwright MCP）進行視覺驗證**
- 不主動重構、不加多餘 docstring / comment
- 不新增我沒要求的功能或抽象層
- Commit 訊息使用 feat/fix/chore + 中文說明

---

## 記憶系統說明

| 層級 | 路徑 | 用途 |
|------|------|------|
| 固定概要 | `CLAUDE.md`（本檔） | 專案架構、偏好、環境 — 手動維護 |
| 近期摘要 | `memory/MEMORY.md` | 近期功能變動重點 — 隨開發更新 |
| 每日日誌 | `memory/daily/YYYY-MM-DD.md` | 每日開發歷程 — 由 `/update-memory` 產生 |
