# Tasks: Chat Response Details and Source Display Fixes

**Input**: Design documents from `/specs/004-chat-response-details/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in specification - tests are omitted from this task list.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/app/`, `frontend/src/`
- All paths shown are absolute from repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and verify environment

- [X] T001 Verify backend and frontend development servers are running
- [X] T002 Verify at least one document exists in knowledge base for testing
- [X] T003 [P] Review existing chat streaming implementation in backend/app/routers/chat.py
- [X] T004 [P] Review existing ChatWindow component in frontend/src/components/chat/ChatWindow.tsx

**Checkpoint**: Development environment ready, existing code understood

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Type definitions and shared interfaces required by all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Add MessageMetadata interface to frontend/src/types/index.ts
- [X] T006 [P] Add TokenUsage interface to frontend/src/types/index.ts
- [X] T007 [P] Add document_id field to SearchResult interface in frontend/src/types/index.ts
- [X] T008 Verify backend already sends metadata in SSE stream (backend/app/routers/chat.py line 83-88)

**Checkpoint**: Type system updated - all user stories can now proceed in parallel

---

## Phase 3: User Story 1 - View Response Metadata (Priority: P1) 🎯 MVP

**Goal**: Display AI response metadata (model, duration, tokens) in a collapsible details section below each assistant message.

**Independent Test**: Send any chat message, receive AI response, verify "詳細資訊" section appears below response (collapsed by default), click to expand and verify metadata displays correctly.

### Implementation for User Story 1

- [X] T009 [P] [US1] Add ExpandedInfoMap interface to frontend/src/components/chat/ChatWindow.tsx
- [X] T010 [P] [US1] Add MessageMetadataMap interface to frontend/src/components/chat/ChatWindow.tsx
- [X] T011 [US1] Add expandedInfo state variable in ChatWindow component (frontend/src/components/chat/ChatWindow.tsx line ~52)
- [X] T012 [US1] Add toggleInfo function in ChatWindow component (frontend/src/components/chat/ChatWindow.tsx line ~90)
- [X] T013 [US1] Add metadata rendering JSX after message content in ChatWindow component (frontend/src/components/chat/ChatWindow.tsx line ~250)
- [X] T014 [US1] Add CSS styles for message-details class in ChatWindow component (frontend/src/components/chat/ChatWindow.tsx bottom of file)
- [X] T015 [US1] Add CSS styles for details-content class in ChatWindow component
- [X] T016 [US1] Add CSS styles for detail-item, detail-label, detail-value classes in ChatWindow component
- [X] T017 [US1] Verify metadata state updates correctly from SSE metadata event (existing code line 178-182)

**Checkpoint**: User Story 1 complete - details section displays metadata, expands/collapses correctly

---

## Phase 4: User Story 2 - Source Documents After Complete Response (Priority: P1) 🎯 MVP

**Goal**: Delay source document display until streaming response has completely finished, preventing sources from appearing during the streaming process.

**Independent Test**: Send a chat query, observe streaming response, verify source documents remain hidden during streaming, verify sources appear immediately after streaming completes.

### Implementation for User Story 2

- [X] T018 [US2] Locate source rendering section in ChatWindow component (frontend/src/components/chat/ChatWindow.tsx line ~300-320)
- [X] T019 [US2] Add messageStreamingStatus check to source rendering condition in ChatWindow component
- [X] T020 [US2] Update source visibility logic to: {!messageStreamingStatus[msg.id] && messageSources[msg.id] && ...}
- [X] T021 [US2] Verify messageStreamingStatus is set to true when streaming starts (existing code line 147)
- [X] T022 [US2] Verify messageStreamingStatus is set to false on "done" event (existing code line 184)

**Checkpoint**: User Story 2 complete - sources only appear after streaming completes

---

## Phase 5: User Story 3 - Fix Document Preview (Priority: P2)

**Goal**: Fix document preview functionality to use correct document_id parameter instead of undefined file_url, eliminating "undefined Internal Server Error".

**Independent Test**: Send a query that returns source documents, wait for sources to appear, click "預覽原檔" button, verify document preview opens successfully in new tab without errors.

### Implementation for User Story 3

- [X] T023 [P] [US3] Update SourcePreviewProps interface to accept documentId parameter in frontend/src/components/chat/SourcePreview.tsx
- [X] T024 [P] [US3] Remove fileUrl parameter from SourcePreviewProps interface
- [X] T025 [US3] Update handlePreview function to validate documentId in SourcePreview component
- [X] T026 [US3] Update handlePreview function to construct correct API URL using documentId in SourcePreview component
- [X] T027 [US3] Add null check for documentId with user-friendly error message in SourcePreview component
- [X] T028 [US3] Return null if documentId is missing to hide preview button in SourcePreview component
- [X] T029 [US3] Update SourcePreview usage in ChatWindow to pass documentId prop (frontend/src/components/chat/ChatWindow.tsx line ~310)
- [X] T030 [US3] Remove fileUrl prop from SourcePreview usage in ChatWindow component
- [X] T031 [US3] Verify backend endpoint /api/kb/documents/{document_id}/file handles requests correctly (backend/app/routers/kb.py line 145-174)

**Checkpoint**: User Story 3 complete - document preview opens successfully without errors

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T032 [P] Verify all TypeScript types are properly exported from frontend/src/types/index.ts
- [X] T033 [P] Add defensive null checks for metadata.tokens in details rendering
- [X] T034 [P] Verify CSS transitions meet 300ms performance target for details toggle
- [X] T035 [P] Test edge case: very fast response (<1 second) still waits for streaming complete
- [X] T036 [P] Test edge case: no sources found - verify no sources section appears
- [X] T037 [P] Test edge case: metadata with null tokens - verify graceful display
- [X] T038 [P] Test edge case: document_id is null - verify preview button hidden
- [X] T039 Code cleanup: Remove any console.log debug statements added during development
- [X] T040 Verify all user-facing text is in Traditional Chinese
- [X] T041 Run through quickstart.md validation checklist manually
- [X] T042 Verify browser console shows no errors during normal chat flow
- [X] T043 [P] Document any deviations from original plan in implementation notes

**Checkpoint**: All polish tasks complete - feature ready for final testing

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User Story 1 (P1): Can proceed independently after Phase 2
  - User Story 2 (P1): Can proceed independently after Phase 2 (but logically after US1 for testing)
  - User Story 3 (P2): Can proceed independently after Phase 2
- **Polish (Phase 6)**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories - fully independent
- **User Story 2 (P1)**: No dependencies on other stories - fully independent (though shares same component as US1)
- **User Story 3 (P2)**: No dependencies on other stories - fully independent (different component)

### Within Each User Story

- **US1**: Tasks T009-T010 can run in parallel (different interfaces), then T011-T017 sequential
- **US2**: Tasks T018-T022 are sequential (all modify same component logic)
- **US3**: Tasks T023-T028 can run in parallel (all modify SourcePreview), then T029-T031 sequential

### Parallel Opportunities

- Phase 1: T003 and T004 can run in parallel (different files)
- Phase 2: T005, T006, T007 can run in parallel (different interfaces)
- Phase 6: All tasks marked [P] can run in parallel (different validations)
- After Phase 2 completes: US1, US2, and US3 can be worked on in parallel by different developers

---

## Parallel Example: User Story 1

```bash
# Launch interface definitions in parallel:
Task: "Add ExpandedInfoMap interface to frontend/src/components/chat/ChatWindow.tsx"
Task: "Add MessageMetadataMap interface to frontend/src/components/chat/ChatWindow.tsx"

# Then sequential implementation:
Task: "Add expandedInfo state variable in ChatWindow component"
Task: "Add toggleInfo function in ChatWindow component"
Task: "Add metadata rendering JSX after message content"
Task: "Add CSS styles for message-details"
```

## Parallel Example: User Story 3

```bash
# Launch SourcePreview modifications in parallel:
Task: "Update SourcePreviewProps interface to accept documentId parameter"
Task: "Remove fileUrl parameter from SourcePreviewProps interface"
Task: "Update handlePreview function to validate documentId"
Task: "Update handlePreview function to construct correct API URL"

# Then sequential ChatWindow updates:
Task: "Update SourcePreview usage in ChatWindow to pass documentId prop"
Task: "Remove fileUrl prop from SourcePreview usage"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2 Only - Both P1)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T008) - CRITICAL
3. Complete Phase 3: User Story 1 (T009-T017)
4. Complete Phase 4: User Story 2 (T018-T022)
5. **STOP and VALIDATE**: Test US1 and US2 together
6. Deploy/demo if ready (US3 can be done later as P2)

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Metadata display works!
3. Add User Story 2 → Test independently → Source timing fixed!
4. **Deploy MVP** (US1 + US2 provide main user value)
5. Add User Story 3 → Test independently → Preview fixed!
6. Run Polish phase → Final deployment

### Parallel Team Strategy

With multiple developers after Phase 2 completes:

1. **Developer A**: User Story 1 (metadata display) - T009-T017
2. **Developer B**: User Story 2 (source timing) - T018-T022
3. **Developer C**: User Story 3 (preview fix) - T023-T031

All three stories can be developed in parallel since they touch different aspects of the chat interface.

---

## Task Statistics

- **Total Tasks**: 43
- **Setup Phase**: 4 tasks
- **Foundational Phase**: 4 tasks (BLOCKING)
- **User Story 1 (P1)**: 9 tasks
- **User Story 2 (P1)**: 5 tasks
- **User Story 3 (P2)**: 9 tasks
- **Polish Phase**: 12 tasks
- **Parallelizable Tasks**: 16 tasks marked [P]
- **Parallel Opportunities**: ~37% of tasks can run concurrently

---

## Notes

- [P] tasks = different files or independent changes, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- All tasks follow the required checklist format with Task ID, labels, and file paths
- No test tasks included (not explicitly requested in spec)
- MVP scope: User Stories 1 & 2 (both P1 priority)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Backend changes minimal (only verification tasks, metadata already implemented)
- Frontend changes focused on state management and conditional rendering
