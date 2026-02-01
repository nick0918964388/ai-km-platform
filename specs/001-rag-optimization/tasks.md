# Tasks: RAG 系統優化

**Input**: Design documents from `/specs/001-rag-optimization/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/app/` for source, `backend/tests/` for tests
- **Frontend**: `src/` for Next.js source code

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, Docker services, and dependencies

- [x] T001 Create docker-compose.yml with Qdrant and Redis services in project root
- [x] T002 [P] Add new dependencies to backend/requirements.txt (cohere, redis, aioredis)
- [x] T003 [P] Create backup directory structure at ./backups/qdrant/
- [x] T004 Update backend/app/config.py with new settings (cohere_api_key, redis_url, qdrant_url, etc.)
- [x] T005 [P] Update backend/.env.example with new environment variables

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Add TaskStatus, ProcessingStep, BackupStatus enums to backend/app/models/schemas.py
- [x] T007 [P] Add ProcessingTask Pydantic model to backend/app/models/schemas.py
- [x] T008 [P] Add BackupRecord Pydantic model to backend/app/models/schemas.py
- [x] T009 [P] Add ProgressMessage Pydantic model to backend/app/models/schemas.py
- [x] T010 Modify backend/app/services/vector_store.py to use persistent Qdrant URL from config
- [x] T011 Create backend/app/services/cache.py with Redis connection and base cache operations

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - 搜尋結果精確度提升 (Priority: P1) 🎯 MVP

**Goal**: 整合 Cohere Reranker 提升專業術語搜尋準確度

**Independent Test**: 輸入專業術語查詢，驗證返回結果的相關性排序是否正確

### Implementation for User Story 1

- [x] T012 [US1] Create backend/app/services/reranker.py with Cohere Rerank client initialization
- [x] T013 [US1] Implement rerank() method in backend/app/services/reranker.py with batch processing
- [x] T014 [US1] Add fallback logic in backend/app/services/reranker.py when API unavailable
- [x] T015 [US1] Modify backend/app/services/rag.py to call reranker after hybrid_search()
- [x] T016 [US1] Add rerank configuration (top_n, model) to search flow in backend/app/services/rag.py
- [x] T017 [US1] Add logging for rerank operations and fallback events in backend/app/services/reranker.py

**Checkpoint**: User Story 1 should be fully functional - search results are now reranked

---

## Phase 4: User Story 2 - 資料持久化與可靠性 (Priority: P2)

**Goal**: Qdrant 持久化模式 + 備份/恢復 API

**Independent Test**: 重啟服務後驗證向量資料是否仍然存在，測試備份/恢復流程

### Implementation for User Story 2

- [x] T018 [US2] Create backend/app/services/backup.py with Qdrant snapshot API integration
- [x] T019 [US2] Implement create_backup() in backend/app/services/backup.py
- [x] T020 [US2] Implement restore_backup() in backend/app/services/backup.py
- [x] T021 [US2] Implement list_backups() and get_backup() in backend/app/services/backup.py
- [x] T022 [US2] Add backup manifest management (./backups/manifest.json) in backend/app/services/backup.py
- [x] T023 [US2] Add POST /api/kb/backups endpoint to backend/app/routers/kb.py
- [x] T024 [US2] Add GET /api/kb/backups endpoint to backend/app/routers/kb.py
- [x] T025 [US2] Add GET /api/kb/backups/{backup_id} endpoint to backend/app/routers/kb.py
- [x] T026 [US2] Add POST /api/kb/backups/{backup_id}/restore endpoint to backend/app/routers/kb.py
- [x] T027 [US2] Add DELETE /api/kb/backups/{backup_id} endpoint to backend/app/routers/kb.py
- [x] T028 [US2] Add GET /api/kb/backups/{backup_id}/download endpoint to backend/app/routers/kb.py

**Checkpoint**: User Story 2 should be fully functional - data persists and can be backed up/restored

---

## Phase 5: User Story 3 - 熱門查詢快速回應 (Priority: P3)

**Goal**: Redis 快取熱門查詢結果，TTL 過期機制

**Independent Test**: 重複查詢相同問題，驗證第二次查詢回應時間 < 100ms

### Implementation for User Story 3

- [x] T029 [US3] Implement query normalization in backend/app/services/cache.py
- [x] T030 [US3] Implement cache_key generation (hash-based) in backend/app/services/cache.py
- [x] T031 [US3] Implement get_cached_results() in backend/app/services/cache.py
- [x] T032 [US3] Implement set_cached_results() with TTL in backend/app/services/cache.py
- [x] T033 [US3] Implement invalidate_cache() for document updates in backend/app/services/cache.py
- [x] T034 [US3] Add cache fallback when Redis unavailable in backend/app/services/cache.py
- [x] T035 [US3] Integrate cache lookup before search in backend/app/services/rag.py
- [x] T036 [US3] Integrate cache storage after search in backend/app/services/rag.py
- [x] T037 [US3] Add cache invalidation on document delete in backend/app/routers/kb.py
- [x] T038 [US3] Add GET /api/cache/stats endpoint to backend/app/routers/kb.py
- [x] T039 [US3] Add POST /api/cache/clear endpoint to backend/app/routers/kb.py

**Checkpoint**: User Story 3 should be fully functional - repeated queries return cached results quickly

---

## Phase 6: User Story 4 - 文件上傳進度追蹤 (Priority: P4)

**Goal**: WebSocket 即時推送文件處理進度

**Independent Test**: 上傳大型文件，驗證前端即時顯示處理進度百分比

### Implementation for User Story 4

- [x] T040 [US4] Create backend/app/services/task_manager.py with Redis-backed task storage
- [x] T041 [US4] Implement create_task() in backend/app/services/task_manager.py
- [x] T042 [US4] Implement update_task() with progress/step updates in backend/app/services/task_manager.py
- [x] T043 [US4] Implement get_task() and list_active_tasks() in backend/app/services/task_manager.py
- [x] T044 [US4] Create backend/app/routers/upload_ws.py with WebSocket endpoint
- [x] T045 [US4] Implement WebSocket connection handler in backend/app/routers/upload_ws.py
- [x] T046 [US4] Implement progress broadcast logic in backend/app/routers/upload_ws.py
- [x] T047 [US4] Modify backend/app/services/document_processor.py to emit progress events
- [x] T048 [US4] Add progress callbacks for parsing step (0-25%) in backend/app/services/document_processor.py
- [x] T049 [US4] Add progress callbacks for chunking step (25-50%) in backend/app/services/document_processor.py
- [x] T050 [US4] Add progress callbacks for embedding step (50-90%) in backend/app/services/document_processor.py
- [x] T051 [US4] Add progress callbacks for indexing step (90-100%) in backend/app/services/document_processor.py
- [x] T052 [US4] Register WebSocket route in backend/app/main.py
- [x] T053 [P] [US4] Create src/hooks/useUploadProgress.ts with WebSocket client
- [x] T054 [P] [US4] Create src/components/UploadProgress.tsx with progress bar and step display
- [x] T055 [US4] Integrate UploadProgress component into existing upload UI in src/app/(main)/admin/knowledge-base/page.tsx

**Checkpoint**: User Story 4 should be fully functional - upload progress is displayed in real-time

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T056 [P] Add hit_count tracking for cached queries in backend/app/services/cache.py
- [x] T057 [P] Add performance logging for rerank latency in backend/app/services/reranker.py
- [x] T058 [P] Add performance logging for cache hit/miss in backend/app/services/cache.py
- [x] T059 Update backend/.env.example with complete configuration documentation
- [x] T060 Run quickstart.md validation - verify all setup steps work correctly
- [x] T061 [P] Add WebSocket reconnection logic in frontend/src/hooks/useUploadProgress.ts

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3 → P4)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 3 (P3)**: Can start after Foundational - No dependencies on other stories
- **User Story 4 (P4)**: Can start after Foundational - No dependencies on other stories

### Within Each User Story

- Services before API endpoints
- Backend before frontend (for US4)
- Core implementation before integration

### Parallel Opportunities

- **Phase 1**: T002, T003, T005 can run in parallel
- **Phase 2**: T007, T008, T009 can run in parallel (after T006 for enums)
- **User Stories**: Once Phase 2 completes, all 4 user stories can start in parallel
- **Within US4**: T053, T054 (frontend) can run in parallel after backend is ready

---

## Parallel Example: Phase 2 Foundation

```bash
# First, create enums (blocking):
Task T006: "Add TaskStatus, ProcessingStep, BackupStatus enums"

# Then launch models in parallel:
Task T007: "Add ProcessingTask Pydantic model"
Task T008: "Add BackupRecord Pydantic model"
Task T009: "Add ProgressMessage Pydantic model"
```

## Parallel Example: User Story 4 Frontend

```bash
# After backend WebSocket is ready, launch frontend in parallel:
Task T053: "Create useUploadProgress.ts hook"
Task T054: "Create UploadProgress.tsx component"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Reranker)
4. **STOP and VALIDATE**: Test search with professional terminology
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 (Reranker) → Test → Deploy (MVP!)
3. Add User Story 2 (Persistence) → Test → Deploy
4. Add User Story 3 (Cache) → Test → Deploy
5. Add User Story 4 (Progress) → Test → Deploy
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Reranker)
   - Developer B: User Story 2 (Persistence/Backup)
   - Developer C: User Story 3 (Cache)
   - Developer D: User Story 4 (WebSocket Progress)
3. Stories complete and integrate independently

---

## Summary

| Phase | Tasks | Parallel Tasks |
|-------|-------|----------------|
| Phase 1: Setup | 5 | 3 |
| Phase 2: Foundational | 6 | 3 |
| Phase 3: US1 Reranker | 6 | 0 |
| Phase 4: US2 Persistence | 11 | 0 |
| Phase 5: US3 Cache | 11 | 0 |
| Phase 6: US4 Progress | 16 | 2 |
| Phase 7: Polish | 6 | 4 |
| **Total** | **61** | **12** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
