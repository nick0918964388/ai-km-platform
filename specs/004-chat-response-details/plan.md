# Implementation Plan: Chat Response Details and Source Display Fixes

**Branch**: `004-chat-response-details` | **Date**: 2026-02-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-chat-response-details/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

This feature enhances the chat interface with three key improvements:
1. **Response Metadata Display**: Add a collapsible details section showing model name, response duration, and token usage for each AI response
2. **Source Document Timing Fix**: Ensure source documents appear only after streaming response completes, not during streaming
3. **Document Preview Fix**: Resolve "undefined Internal Server Error" when clicking document preview buttons

Technical approach involves frontend state management updates to track streaming completion separately from loading state, backend API modifications to return response metadata, and proper document_id handling in the preview flow.

## Technical Context

**Language/Version**: Python 3.10+ (Backend), TypeScript 5.x strict mode (Frontend)
**Primary Dependencies**:
- Backend: FastAPI 0.109+, Pydantic 2.6+, Qdrant, SQLAlchemy 2.0+, OpenAI SDK
- Frontend: Next.js 16.1.6, React 19.2.3, IBM Carbon 1.100.0, Zustand 5.0.10
**Storage**: PostgreSQL (structured data), Qdrant (vector storage), local filesystem (documents)
**Testing**: pytest (backend), Jest/React Testing Library (frontend)
**Target Platform**: Web application (Linux/Docker server backend, modern browsers frontend)
**Project Type**: Web (backend API + frontend SPA)
**Performance Goals**:
- Source document display <100ms after streaming completes (SC-002)
- Details section toggle <300ms with smooth animation (SC-004)
- API response times maintain <200ms p95 (Constitution Principle II)
**Constraints**:
- Must not break existing chat functionality
- Must handle streaming and non-streaming responses gracefully
- Must work with existing IBM Carbon UI components
- Token usage data may not always be available from OpenAI API
**Scale/Scope**: Single chat interface enhancement affecting ~3 backend endpoints, ~4 frontend components, and state management

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: 程式碼品質 (Code Quality)
✅ **PASS**: Implementation will use Python 3.10+ with type hints and TypeScript strict mode. All code follows existing patterns with type annotations.

### Principle II: 效能優先 (Performance First)
✅ **PASS**:
- Source document display target <100ms after streaming (SC-002) - well under 500ms vector search requirement
- Details toggle <300ms (SC-004) - UI-only operation, no API impact
- No new API endpoints affecting p95 latency; only modifying response payloads

### Principle III: 可維護性 (Maintainability)
✅ **PASS**:
- Changes localized to chat router and ChatWindow component
- Uses existing service layer separation (rag.py for business logic)
- No new architectural patterns introduced
- Updates consistent with existing streaming response structure

### Principle IV: 中文優先 (Chinese-First)
✅ **PASS**:
- UI labels in Traditional Chinese: "詳細資訊", "預覽原檔"
- No changes to document processing or terminology handling
- Metadata display language-agnostic (numbers, technical terms)

### Principle V: 安全性 (Security)
✅ **PASS**:
- No new authentication requirements (uses existing API auth)
- No sensitive data in metadata (model name, duration, token counts are non-sensitive)
- Document preview uses existing document_id validation
- Error messages will not expose internal system details

**Overall Status**: ✅ ALL GATES PASSED - Proceed to Phase 0

---

## Constitution Check Re-evaluation (Post-Phase 1 Design)

*Re-evaluated after completing data model, contracts, and architecture design.*

### Principle I: 程式碼品質 (Code Quality)
✅ **PASS** (confirmed):
- All TypeScript interfaces defined with strict typing in `contracts/component-interfaces.md`
- Python type hints maintained in existing backend code (no changes to rag.py)
- Type guards and validation utilities documented for null safety

### Principle II: 效能優先 (Performance First)
✅ **PASS** (confirmed):
- Source display timing: Client-side conditional render (~10ms, well under 100ms target)
- Details toggle: Native `<details>` HTML with CSS transitions (~200ms, under 300ms target)
- Metadata storage: O(1) object key access, ~300 bytes per message (negligible)
- No additional network calls introduced

### Principle III: 可維護性 (Maintainability)
✅ **PASS** (confirmed):
- Changes isolated to chat module (no cross-cutting concerns)
- Service layer separation maintained (rag.py unchanged)
- Clear interfaces documented in `contracts/component-interfaces.md`
- Backward compatible (graceful degradation for missing data)

### Principle IV: 中文優先 (Chinese-First)
✅ **PASS** (confirmed):
- All UI labels in Traditional Chinese: "詳細資訊", "預覽原檔", "模型", "回應時間", "Token 使用"
- Error messages in Chinese: "無法預覽：缺少文件識別碼"
- No impact on document processing or terminology handling

### Principle V: 安全性 (Security)
✅ **PASS** (confirmed):
- No new authentication endpoints (uses existing API auth)
- Input validation for document_id before preview
- Error messages do not expose internals (sanitized in SourcePreview.tsx)
- No sensitive data in metadata (model name, timing, token counts are non-sensitive)

**Final Status**: ✅ ALL GATES PASSED - Proceed to Phase 2 (Task Generation)

**Design Complexity Assessment**: No additional complexity introduced beyond stated requirements. Implementation uses standard React patterns and HTML features.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   ├── chat.py              # Modify: streaming endpoint metadata
│   │   └── kb.py                # Modify: document preview error handling
│   ├── services/
│   │   └── rag.py               # Modify: return token usage in metadata
│   └── models/
│       └── schemas.py           # Review: ensure metadata types defined
└── tests/
    └── test_chat_stream.py      # Add: verify metadata in stream response

frontend/
├── src/
│   ├── components/
│   │   └── chat/
│   │       ├── ChatWindow.tsx   # Modify: streaming status, details UI
│   │       └── SourcePreview.tsx # Review: document_id handling
│   ├── types/
│   │   └── index.ts             # Modify: add MessageMetadata types
│   └── store/
│       └── useStore.ts          # Review: message state management
└── tests/
    └── chat/                     # Add: component tests for details section
```

**Structure Decision**: Web application (Option 2) with FastAPI backend and Next.js frontend. Changes are focused on the chat module with minimal cross-cutting concerns. Both backend and frontend modifications are isolated to chat-related files.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations detected. This feature follows existing architectural patterns and requires no additional complexity justification.
