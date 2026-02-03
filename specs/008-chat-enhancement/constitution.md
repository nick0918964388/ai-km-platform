# Constitution - Chat Enhancement

## Project Principles

1. **漸進式增強**: 在現有架構上新增功能，不破壞現有行為
2. **Streaming 優先**: 所有新的後端資料透過現有 SSE streaming 機制傳遞
3. **類型安全**: 前後端都維持強型別（TypeScript strict + Pydantic）
4. **使用者體驗**: UI 變動要自然融入現有設計語言（CSS variables + Carbon icons）
5. **最小依賴**: 儘量不引入新的套件依賴

## Tech Stack
- Backend: Python 3.10+ / FastAPI / OpenAI SDK
- Frontend: Next.js / React / TypeScript strict / Carbon Design
- Vector DB: Qdrant (Docker)
- Database: PostgreSQL

## Constraints
- 不改動現有 API 的 response schema（只新增欄位）
- Modal 使用純 CSS/React，不引入新 UI library
- Follow-up questions 使用同一個 OpenAI model (gpt-4o)
