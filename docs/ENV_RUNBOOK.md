# Production .env Runbook

> 若 prod `/root/ai-km-platform/.env` 遺失或被損壞，照本檔重建。
> **本檔不含任何實際值、hash、或密碼** — 僅記錄結構與流程。
>
> **需 docker compose v2.x+**。驗證：`docker compose version | grep 'v2\|v3'`

---

## 必填 env keys

| Key | 用途 | 取值方式 | 遺失後果 | 輪替頻率 |
|-----|------|----------|----------|----------|
| `JWT_SECRET` | JWT 簽章 | `openssl rand -hex 32` | backend 拒絕啟動；換新值 = 所有 session 立即失效 | 季度 |
| `NEO4J_PASSWORD` | Neo4j 連線密碼 | 自訂強密碼（>=16 字元，混合大小寫+數字+符號） | Neo4j 無法連線；已有資料需用舊密碼才能 restart | 年度 |
| `GITHUB_RUNNER_TOKEN` | Self-hosted runner 首次註冊 | GitHub → Repo Settings → Actions → Runners → New runner | **僅首次註冊需要**；runner 已上線後可填任意非空字串 | 1 小時 TTL（首次使用後即失效） |
| `AIKM_API_KEY` | 前後端 API 識別 | 自訂隨機字串（建議 `openssl rand -hex 16`） | API 認證失敗（若後端有啟用） | 視需要 |

---

## Optional（有預設值，建議明列於 .env 避免隱性行為）

| Key | 預設值 | 說明 |
|-----|--------|------|
| `RERANKER_PROVIDER` | `ollama` | reranker provider：`ollama` 或 `cohere` |
| `OLLAMA_RERANKER_URL` | `http://ollama.webtw.xyz:11434` | Ollama reranker 端點 |
| `OLLAMA_RERANKER_MODEL` | `linux6200/bge-reranker-v2-m3:latest` | Ollama reranker 模型 |
| `COHERE_API_KEY` | 空 | Cohere reranker API key（`RERANKER_PROVIDER=cohere` 時必填） |
| `OPENAI_API_KEY` | 空 | OpenAI fallback LLM（選用） |
| `JINA_API_KEY` | 空 | Jina embedding API key（選用） |
| `ANTHROPIC_API_KEY` | 空 | Maximo tool-router (012) 所需（選用） |
| `PG_VIEWER_DATABASE_URL` | 空 | PostgreSQL Viewer (013) 專用 read-only 連線字串 |
| `PG_VIEWER_PASSWORD` | 空 | PG Viewer admin 密碼 |
| `PG_VIEWER_AUDIT_PURGER_PASSWORD` | 空 | PG Viewer 稽核日誌清除密碼 |

---

## 災難恢復 SOP

```bash
# 1. SSH 進部署機
ssh user@192.168.1.11

# 2. 切換到專案目錄
cd /root/ai-km-platform

# 3. 以 example 為基礎重建 .env
cp .env.example .env

# 4. 依上方「必填 env keys」表格補齊每個必填值
#    以編輯器打開，逐一填入
nano .env  # 或 vim .env

# 5. 驗證 compose 不報錯（會立即顯示缺失的必填 key）
docker compose config > /dev/null

# 6. 重建並啟動 backend + frontend
docker compose up -d --build backend frontend

# 7. 健康檢查
curl http://localhost:8000/health
```

> **注意：** `docker compose config` 在遇到 `${VAR:?error}` 且 VAR 為空時，會立即輸出錯誤並 exit 1。這是設計行為，確保空 secret 在啟動前就被攔截。

---

## 變更日誌

所有 prod `.env` 變動 **必須** 記錄到 `/root/ai-km-platform/.env.changelog`，格式：

```
YYYY-MM-DD HH:MM | 操作人 | 改動摘要
```

範例：

```
2026-04-22 14:30 | nick | 輪替 JWT_SECRET（季度例行）
2026-04-10 09:00 | nick | 首次部署，建立完整 .env
```

---

## Neo4j 密碼輪替 SOP

Neo4j 首次啟動會將 `NEO4J_AUTH` 密碼寫入 volume，之後改 env var 不會同步 DB 內部密碼。
改密碼必須走 `ALTER USER`。

步驟：

1. 登入目前密碼確認：
   ```bash
   docker exec aikm-neo4j cypher-shell -u neo4j -p '<當前>' "RETURN 1"
   ```
2. 在 Neo4j 內改密碼：
   ```bash
   docker exec aikm-neo4j cypher-shell -u neo4j -p '<當前>' "ALTER USER neo4j SET PASSWORD '<新>'"
   ```
3. 改 `.env` 的 `NEO4J_PASSWORD`
4. 驗證 compose config：
   ```bash
   docker compose config > /dev/null
   ```
5. 重啟 backend（需要重讀 env）：
   ```bash
   docker compose up -d backend
   ```
6. 驗證連線：
   ```bash
   curl http://localhost:8000/health
   ```

> ⚠️ **若弄丟舊密碼**：需備份後清 `aikm-neo4j-data` volume 重建（資料會遺失，有備份才能做）

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `.env.example` | 所有 key 的空白模板（已提交至 git） |
| `scripts/check_env_drift.sh` | CI 腳本：確保 `.env.example` 涵蓋 `docker-compose.yml` 所有變數 |
| `docker-compose.yml` | 必填 key 使用 `${VAR:?error}` 語法，空值啟動即失敗 |
