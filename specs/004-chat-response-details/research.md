# Research: Chat Response Details and Source Display Fixes

**Feature**: 004-chat-response-details
**Date**: 2026-02-02
**Purpose**: Resolve unknowns and establish technical approach for implementation

## Research Areas

### 1. OpenAI Token Usage Tracking

**Question**: How do we reliably capture token usage from OpenAI streaming API?

**Findings**:
- OpenAI SDK (Python) supports `stream_options={"include_usage": True}` parameter in streaming mode
- Token usage data appears in the **final chunk** of the stream with `chunk.usage` attribute
- Current implementation in `rag.py:498` already captures this correctly:
  ```python
  stream = client.chat.completions.create(
      model="gpt-4o",
      stream=True,
      stream_options={"include_usage": True},  # ✓ Already enabled
  )
  ```
- Usage data structure: `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}`

**Decision**: Use existing OpenAI streaming with `include_usage` flag. No changes needed to token capture logic in `rag.py`. Token data is already yielded as `{"type": "usage", "data": usage_info}` in line 515.

**Rationale**: Existing implementation already correctly captures token usage. We only need to surface this data in the frontend UI.

---

### 2. Streaming Completion Detection

**Question**: How do we reliably detect when streaming has finished versus when loading is complete?

**Findings**:
- Current implementation uses two separate state flags:
  - `isLoading`: General API request state (lines 46, 121, 209)
  - `messageStreamingStatus`: Per-message streaming state (lines 51, 147, 184, 187)
- Backend sends `{"type": "done"}` event when streaming completes (backend/app/routers/chat.py:91)
- Frontend sets `messageStreamingStatus[messageId] = false` on receiving "done" event (line 184)
- Sources are sent FIRST in the stream (line 62 in backend), before content chunks

**Current Problem**: Sources are displayed immediately when received, not waiting for streaming completion.

**Decision**: Add new state tracking to delay source visibility until `messageStreamingStatus[messageId]` becomes `false`.

**Rationale**: Separating streaming status from loading status allows precise control over when sources appear. The "done" event provides a reliable signal for streaming completion.

---

### 3. IBM Carbon Collapsible Component Patterns

**Question**: What is the best way to implement a collapsible details section with IBM Carbon?

**Findings**:
- IBM Carbon provides `Accordion` component for collapsible content
- Alternative: Use HTML `<details>` + `<summary>` with custom Carbon-styled CSS
- Current codebase uses Carbon components extensively (`@carbon/react`, `@carbon/icons-react`)
- Existing UI patterns favor inline styled components with Carbon color variables

**Decision**: Use native HTML `<details>`/`<summary>` elements with Carbon-styled CSS.

**Rationale**:
- Simpler implementation (no additional imports needed)
- Better accessibility out-of-the-box
- Consistent with existing ChatWindow styling approach (inline CSS with Carbon variables)
- Lightweight (no extra bundle size)

**Alternatives Considered**:
- **Carbon Accordion**: More heavyweight, requires additional imports, overkill for single collapsible section
- **Custom div + state**: More complex state management for simple expand/collapse behavior

---

### 4. Document Preview Error Handling

**Question**: Why does the document preview show "undefined Internal Server Error"?

**Findings**:
- Current `SourcePreview.tsx` directly opens URL from `fileUrl` prop (line 17)
- Backend endpoint `/api/kb/documents/{document_id}/file` expects `document_id` parameter (kb.py:145)
- `SearchResult` schema includes `file_url` but preview likely needs `document_id` instead
- Error message "undefined" suggests frontend is trying to access undefined `document_id`

**Root Cause**: Mismatch between what frontend sends and what backend expects. Frontend constructs URL from `fileUrl` string, but backend needs `document_id` as path parameter.

**Decision**:
1. Modify `SourcePreview.tsx` to accept `documentId` prop and construct correct API path
2. Update `ChatWindow.tsx` to pass `documentId` from `SearchResult` to `SourcePreview`
3. Add proper error handling in `SourcePreview` for missing/null `documentId`

**Rationale**: Fix the data flow to match backend API contract. Backend already has proper error handling (kb.py:158-172); we just need to send the right parameter.

---

### 5. Performance Considerations

**Question**: How do we ensure sub-100ms source display after streaming and sub-300ms details toggle?

**Findings**:
- Source display timing: React state updates are synchronous within same render cycle
- Setting `messageStreamingStatus` to `false` will immediately allow conditional rendering of sources
- CSS transitions for details/summary: Native browser animation, typically 150-200ms
- No network calls involved in either operation

**Decision**:
- Use React conditional rendering `{!messageStreamingStatus[msg.id] && sources && <SourcesSection />}`
- Use CSS `transition: all 0.2s ease` for details element animation

**Rationale**: Both operations are client-side only with minimal computational overhead. React's reconciliation and browser CSS transitions are well-optimized and will easily meet performance targets.

---

## Technology Choices Summary

| Component | Technology | Justification |
|-----------|------------|---------------|
| Token tracking | Existing OpenAI `stream_options` | Already implemented, no changes needed |
| Streaming detection | `messageStreamingStatus` state + "done" event | Precise control, already exists |
| Collapsible UI | HTML `<details>`/`<summary>` + Carbon CSS | Native, accessible, lightweight |
| State management | Existing Zustand store + local state | Consistent with current architecture |
| Error handling | Prop validation + null checks | Defensive programming at component boundary |

---

## Implementation Dependencies

1. **No new dependencies required** - All features achievable with existing stack
2. **No breaking changes** - Additive changes only, backward compatible
3. **Reuses existing patterns**:
   - SSE streaming event handling (already in ChatWindow.tsx)
   - Token metadata flow (already in rag.py and chat.py)
   - Carbon styling conventions (already throughout codebase)

---

## Risk Assessment

**Low Risk Areas**:
- Token metadata display: Data already captured, just needs UI
- Details section toggle: Standard HTML feature with CSS styling
- Streaming detection: Logic already exists, just needs to control source visibility

**Medium Risk Areas**:
- Document preview fix: Requires understanding current `SearchResult.file_url` structure
  - Mitigation: Add defensive null checks and clear error messages

**High Risk Areas**:
- None identified

---

## Open Questions Resolved

All initial unknowns from Technical Context have been resolved:
- ✅ How to track OpenAI token usage: Use `stream_options={"include_usage": True}`
- ✅ How to detect streaming completion: Use existing `messageStreamingStatus` + "done" event
- ✅ What UI component for collapsible section: HTML `<details>`/`<summary>`
- ✅ How to fix document preview: Pass correct `document_id` to backend endpoint
- ✅ How to meet performance targets: Client-side operations with CSS transitions

---

## Next Steps

Proceed to Phase 1:
1. Generate `data-model.md` with entity definitions
2. Generate API contracts in `/contracts/` directory
3. Create `quickstart.md` for development setup
4. Update agent context with any new patterns introduced
