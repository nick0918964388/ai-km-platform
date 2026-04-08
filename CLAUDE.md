# ai-km-platform Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-01

## Active Technologies
- Python 3.10+ (Backend), TypeScript strict mode (Frontend) + FastAPI, Qdrant, Redis, Cohere SDK (Backend) / Next.js 14, React 18, IBM Carbon (Frontend) (002-document-preview)
- 本地檔案系統 `./storage/documents/`，Qdrant 向量資料庫 (002-document-preview)
- PostgreSQL (新增，結構化資料), Qdrant (現有，向量儲存) (003-structured-data-query)
- Python 3.10+ (Backend), TypeScript 5.x strict mode (Frontend) (004-chat-response-details)
- PostgreSQL (structured data), Qdrant (vector storage), local filesystem (documents) (004-chat-response-details)
- TypeScript 5.x strict mode, Next.js 16.1.6, React 19.2.3 + Tailwind CSS v4, @carbon/react v1.100.0, @carbon/icons-react v11.74.0 (006-rwd)
- N/A (frontend-only changes) (006-rwd)
- Python 3.10+ (Backend), TypeScript 5.x strict mode (Frontend) + FastAPI 0.109+, Pydantic 2.x, Pillow 10.x (Backend) / React 19, Next.js 16.1, IBM Carbon v1.100, Tailwind CSS v4 (Frontend) (009-profile-dashboard)
- SQLite (user profiles), Qdrant (activity logs, query history), Local filesystem (avatar images at `./storage/avatars/`) (009-profile-dashboard)
- Python 3.14 (backend), TypeScript (frontend - 無變更) + FastAPI, sentence-transformers (BGE model), cohere (existing) (010-reranker-integration)
- N/A (無新增儲存需求，模型快取使用 Hugging Face 預設路徑) (010-reranker-integration)
- TypeScript 5.x (strict mode), React 19.2.3, Next.js 15.5.11 + Recharts 2.15.4, @carbon/react 1.100.0, Tailwind CSS v4 (011-dashboard-charts)
- N/A (frontend-only component, no persistence required) (011-dashboard-charts)

- Python 3.10+ (Backend), TypeScript strict mode (Frontend) + FastAPI, Qdrant, Redis, Cohere SDK, Next.js (001-rag-optimization)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.10+ (Backend), TypeScript strict mode (Frontend): Follow standard conventions

## Recent Changes
- 011-dashboard-charts: Added TypeScript 5.x (strict mode), React 19.2.3, Next.js 15.5.11 + Recharts 2.15.4, @carbon/react 1.100.0, Tailwind CSS v4
- 010-reranker-integration: Added Python 3.14 (backend), TypeScript (frontend - 無變更) + FastAPI, sentence-transformers (BGE model), cohere (existing)
- 009-profile-dashboard: Added Python 3.10+ (Backend), TypeScript 5.x strict mode (Frontend) + FastAPI 0.109+, Pydantic 2.x, Pillow 10.x (Backend) / React 19, Next.js 16.1, IBM Carbon v1.100, Tailwind CSS v4 (Frontend)


<!-- MANUAL ADDITIONS START -->

## ⚠️ CRITICAL RULES (MUST FOLLOW)
1. **DOCKER ONLY**: All services (Backend, Frontend, DB, Redis, Qdrant) MUST be run via Docker Compose.
   - ❌ **FORBIDDEN**: `npm run dev`, `uvicorn app.main:app`, `python main.py` on host machine.
   - ✅ **ALLOWED**: `docker compose up -d`, `docker compose logs -f`
   - **Reason**: Ensure environment consistency and dependency isolation.

2. **REBUILD ON CHANGE**: When backend code changes, you MUST rebuild the container (unless using volume mounts, but current setup requires rebuild).
   - Command: `docker compose up -d --build backend`

## Docker Commands
- **Start All**: `docker compose up -d`
- **Rebuild Backend**: `docker compose up -d --build backend`
- **Rebuild Frontend**: `docker compose up -d --build frontend`
- **Logs**: `docker compose logs -f [service_name]`
- **Stop**: `docker compose down`

<!-- MANUAL ADDITIONS END -->
