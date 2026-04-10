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

## 測試環境

| 項目 | 值 |
|------|----|
| 目標主機 | 192.168.1.11 |
| API URL | `http://192.168.1.11:8000` |
| Frontend | `http://192.168.1.11:3000` |
| 遷移日期 | 2026-04-09（從 Mac Mini 遷移） |

**Mac Mini 上同時運行**：Drone CI (8090)、Maximo Liberty (9080/9443)，停止 aikm 服務時勿影響這些服務。

### Docker 服務清單
| 服務 | Container | Port |
|------|-----------|------|
| Frontend | aikm-frontend | 3000 |
| Backend | aikm-backend | 8000 |
| PostgreSQL | aikm-postgres | 5432 |
| Redis | aikm-redis | 6379 |
| Qdrant | aikm-qdrant | 6333/6334 |

---

## ⚠️ 強制規則

1. **DOCKER ONLY** — 所有服務必須透過 Docker Compose 運行
   - ❌ 禁止：`npm run dev`、`uvicorn`、`python main.py`（在 host 執行）
   - ✅ 允許：`docker compose up -d`

2. **後端異動必須重建容器**
   - `docker compose up -d --build backend`

### 常用 Docker 指令
```bash
docker compose up -d                        # 啟動全部
docker compose up -d --build backend        # 重建後端
docker compose up -d --build frontend       # 重建前端
docker compose logs -f [service_name]       # 看 logs
docker compose down                         # 停止全部
```

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
