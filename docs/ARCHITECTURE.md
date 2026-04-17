# 系統架構文檔

## 整體架構

AIKM 採用前後端分離的微服務架構，包含三個主要資料層：向量儲存、關聯式資料庫和快取層。

```
┌────────────────────────────────────────────────────────────────────┐
│                          Client Layer                               │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    Next.js Frontend (Port 3000)               │ │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐│ │
│  │  │   Chat     │ │  Knowledge │ │ Dashboard  │ │  Settings  ││ │
│  │  │  Interface │ │   Base     │ │  Analytics │ │   Admin    ││ │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘│ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ HTTP/SSE
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                       API Gateway Layer                             │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              FastAPI Backend (Port 8000)                      │ │
│  │  ┌─────────────────────────────────────────────────────────┐ │ │
│  │  │                    Middleware                            │ │ │
│  │  │  • CORS • API Key Auth • Request Logging                 │ │ │
│  │  └─────────────────────────────────────────────────────────┘ │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │ │
│  │  │ /api/chat│ │/api/kb/* │ │/api/query│ │/api/structured │  │ │
│  │  │  Router  │ │  Router  │ │  Router  │ │    Router      │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                        Service Layer                                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                      Core Services                           │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐│  │
│  │  │    RAG     │  │   Intent   │  │      Document          ││  │
│  │  │  Service   │  │ Classifier │  │     Processor          ││  │
│  │  │ (Retrieve  │  │ (Routing)  │  │  (PDF/Word/Excel/Img)  ││  │
│  │  │ +Generate) │  │            │  │                        ││  │
│  │  └────────────┘  └────────────┘  └────────────────────────┘│  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐│  │
│  │  │  NL2SQL    │  │  Reranker  │  │      Embedding         ││  │
│  │  │  Service   │  │  (Cohere)  │  │      Service           ││  │
│  │  │            │  │            │  │ (Sentence-Transformers)││  │
│  │  └────────────┘  └────────────┘  └────────────────────────┘│  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                         Data Layer                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │     Qdrant     │  │   PostgreSQL   │  │       Redis        │   │
│  │  (Port 6333)   │  │  (Port 5432)   │  │   (Port 6379)      │   │
│  │                │  │                │  │                    │   │
│  │ • text_chunks  │  │ • vehicles     │  │ • Query Cache      │   │
│  │ • embeddings   │  │ • faults       │  │ • Embedding Cache  │   │
│  │ • metadata     │  │ • maintenance  │  │ • Session Data     │   │
│  │                │  │ • costs        │  │                    │   │
│  │                │  │ • inventory    │  │                    │   │
│  └────────────────┘  └────────────────┘  └────────────────────┘   │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                   File Storage                              │   │
│  │              ./backend/storage/documents/                   │   │
│  │          (原始文件儲存，支援線上預覽)                         │   │
│  └────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

## 技術棧詳細說明

### Frontend

| 技術 | 版本 | 用途 |
|------|------|------|
| Next.js | 16.1.6 | React 全端框架，App Router |
| React | 19.2.3 | UI 元件框架 |
| TypeScript | 5.x | 型別安全 |
| IBM Carbon React | 1.100.0 | 企業級 UI 元件庫 |
| Tailwind CSS | v4 | 原子化 CSS 框架 |
| Zustand | 5.0.10 | 輕量級狀態管理 |
| Recharts | 2.15.4 | 資料視覺化圖表 |
| react-markdown | 10.1.0 | Markdown 渲染 |

### Backend

| 技術 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 程式語言 |
| FastAPI | 0.109+ | 非同步 Web 框架 |
| Uvicorn | 0.27+ | ASGI 伺服器 |
| SQLAlchemy | 2.0+ | ORM (async) |
| Alembic | 1.13+ | 資料庫遷移 |
| Pydantic | 2.6+ | 資料驗證 |

### AI/ML

| 技術 | 用途 |
|------|------|
| Sentence Transformers (all-MiniLM-L6-v2) | 文本嵌入 |
| OpenAI GPT-4o | LLM 推理、回答生成 |
| Cohere Rerank v3.5 | 語義重排序 |
| PyMuPDF / pdfplumber | PDF 解析 |
| python-docx | Word 文件處理 |
| openpyxl / xlrd | Excel 文件處理 |

### 資料儲存

| 服務 | 版本 | 用途 |
|------|------|------|
| Qdrant | v1.12.5 | 向量資料庫，儲存文件嵌入 |
| PostgreSQL | 16 Alpine | 關聯式資料庫，結構化資料 |
| Redis | 7 Alpine | 快取層，查詢結果快取 |

## RAG Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAG Pipeline                              │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│  │  Query   │───▶│ Embedding│───▶│  Vector  │───▶│ Reranker │ │
│  │  Input   │    │  Service │    │  Search  │    │ (Cohere) │ │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│                                                        │        │
│                                                        ▼        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│  │ Response │◀───│   LLM    │◀───│  Prompt  │◀───│ Context  │ │
│  │ (Stream) │    │ (GPT-4o) │    │ Builder  │    │ Builder  │ │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│       │                                                         │
│       ▼                                                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Post-processing                                 │  │
│  │  • Follow-up Questions Generation                         │  │
│  │  • Source Relevance Scoring (≥0.5 threshold)              │  │
│  │  • Metadata Extraction                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 文件處理流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Document Processing                           │
│                                                                  │
│  ┌──────────┐    ┌──────────────────────────────────────────┐  │
│  │  Upload  │───▶│              Document Processor           │  │
│  │   File   │    │  ┌────────┐ ┌────────┐ ┌────────────────┐│  │
│  └──────────┘    │  │  PDF   │ │  Word  │ │    Excel       ││  │
│                  │  │ Parser │ │ Parser │ │    Parser      ││  │
│                  │  └────────┘ └────────┘ └────────────────┘│  │
│                  │  ┌────────────────────────────────────────┐│ │
│                  │  │           Image Processor             ││  │
│                  │  │  • OCR (Vision) • CLIP Embedding      ││  │
│                  │  └────────────────────────────────────────┘│ │
│                  └──────────────────────────────────────────┘  │
│                                    │                            │
│                                    ▼                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 Chunking Strategy                         │  │
│  │  • Recursive Text Splitter                                │  │
│  │  • Chunk Size: 500 tokens (overlap: 50)                   │  │
│  │  • Preserve document structure (headers, tables)          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                    │                            │
│                                    ▼                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐     │
│  │  Embedding  │───▶│   Store in  │───▶│   Save Original │     │
│  │  Generation │    │   Qdrant    │    │   to Storage    │     │
│  └─────────────┘    └─────────────┘    └─────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## 目錄結構

```
ai-km-platform/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 應用入口
│   │   ├── config.py            # 設定管理
│   │   ├── db/
│   │   │   └── session.py       # 資料庫連線
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic schemas
│   │   ├── routers/
│   │   │   ├── chat.py          # 聊天 API
│   │   │   ├── kb.py            # 知識庫管理
│   │   │   ├── query.py         # 統一查詢 API
│   │   │   ├── structured.py    # 結構化資料 API
│   │   │   ├── dashboard.py     # 儀表板 API
│   │   │   └── export.py        # 匯出功能
│   │   └── services/
│   │       ├── rag.py           # RAG 核心服務
│   │       ├── document_processor.py
│   │       ├── embedding.py
│   │       ├── vector_store.py
│   │       ├── reranker.py
│   │       ├── intent_classifier.py
│   │       ├── nl2sql_service.py
│   │       └── cache.py
│   ├── alembic/                 # 資料庫遷移
│   ├── storage/documents/       # 原始文件儲存
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js App Router
│   │   │   ├── (main)/
│   │   │   │   ├── chat/        # 聊天頁面
│   │   │   │   ├── admin/       # 管理後台
│   │   │   │   └── history/     # 歷史記錄
│   │   │   └── (auth)/
│   │   │       └── login/       # 登入頁面
│   │   ├── components/
│   │   │   ├── chat/            # 聊天元件
│   │   │   ├── layout/          # 版面元件
│   │   │   └── dashboard/       # 儀表板元件
│   │   ├── hooks/               # React Hooks
│   │   ├── services/            # API 服務層
│   │   ├── store/               # Zustand 狀態
│   │   └── types/               # TypeScript 型別
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── docs/
    ├── ARCHITECTURE.md
    ├── API.md
    └── FEATURES.md
```

## 部署架構

### 開發環境

```
Developer Machine
├── Frontend: http://localhost:3000 (npm run dev)
├── Backend: http://localhost:8000 (uvicorn --reload)
├── PostgreSQL: localhost:5432 (Docker)
├── Qdrant: localhost:6333 (Docker)
└── Redis: localhost:6379 (Docker)
```

### 生產環境

```
Production Server
├── Frontend: https://aikm.nickai.cc (Docker)
├── Backend: https://aikmbackend.nickai.cc (Docker)
├── PostgreSQL: Internal network (Docker)
├── Qdrant: Internal network (Docker)
└── Redis: Internal network (Docker)
```

## 安全考量

1. **API 認證** - 使用 `X-API-Key` header 進行 API 認證
2. **CORS** - 限制允許的來源網域
3. **資料隔離** - 資料庫服務僅在內部網路可存取
4. **敏感資料** - API Keys 透過環境變數注入，不進版本控制
