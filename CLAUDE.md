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
- 006-rwd: Added TypeScript 5.x strict mode, Next.js 16.1.6, React 19.2.3 + Tailwind CSS v4, @carbon/react v1.100.0, @carbon/icons-react v11.74.0
- 004-chat-response-details: Added Python 3.10+ (Backend), TypeScript 5.x strict mode (Frontend)
- 003-structured-data-query: Added Python 3.10+ (Backend), TypeScript strict mode (Frontend)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
