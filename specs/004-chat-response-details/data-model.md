# Data Model: Chat Response Details and Source Display Fixes

**Feature**: 004-chat-response-details
**Date**: 2026-02-02
**Purpose**: Define data entities, structures, and relationships for the feature

## Entity Overview

This feature introduces three new data entities and modifies existing message state management:

1. **MessageMetadata** (new): Response metadata for each assistant message
2. **StreamingStatus** (new): Per-message streaming completion tracking
3. **ExpandedInfoMap** (new): UI state for details section visibility
4. **SearchResult** (modified): Add document_id tracking for preview

---

## Entity Definitions

### 1. MessageMetadata

**Purpose**: Store technical metadata about each AI response for transparency and debugging.

**Structure** (TypeScript):
```typescript
interface MessageMetadata {
  model: string;              // AI model used (e.g., "gpt-4o")
  duration_ms: number;        // Total response time in milliseconds
  tokens: TokenUsage | null;  // Token consumption details, null if unavailable
}

interface TokenUsage {
  prompt_tokens: number;      // Tokens in the prompt
  completion_tokens: number;  // Tokens in the completion
  total_tokens: number;       // Sum of prompt + completion
}
```

**Validation Rules**:
- `model`: Non-empty string, max 50 characters
- `duration_ms`: Positive integer (>= 0)
- `tokens`: Object with all three fields as positive integers, OR null
- All fields MUST be present; null values only allowed for `tokens`

**Lifecycle**:
- **Created**: When backend sends `{"type": "metadata", "data": {...}}` event
- **Stored**: In React component state `messageMetadata: MessageMetadataMap`
- **Displayed**: In collapsible details section below message
- **Persisted**: No (ephemeral, lost on page refresh)

**State Management**:
```typescript
interface MessageMetadataMap {
  [messageId: string]: MessageMetadata;
}

// Usage
const [messageMetadata, setMessageMetadata] = useState<MessageMetadataMap>({});
```

---

### 2. StreamingStatus

**Purpose**: Track whether a specific message is currently streaming to control source document visibility.

**Structure** (TypeScript):
```typescript
interface StreamingStatus {
  [messageId: string]: boolean;
}
```

**State Transitions**:
```
null/undefined → true   : When streaming starts (message added to chat)
true → false            : When backend sends {"type": "done"} event
false → [no change]     : Terminal state (streaming completed)
```

**Validation Rules**:
- Key: Must be valid message ID (string)
- Value: Boolean only (true = streaming, false = completed)

**Lifecycle**:
- **Initialized**: When assistant message is first added to conversation
- **Set to true**: Immediately after `addMessage(convId!, assistantMessage)`
- **Set to false**: On receiving `data.type === 'done'` in SSE stream
- **Cleaned up**: When message is removed (not implemented, messages persist)

**Current Implementation**:
```typescript
// Already exists in ChatWindow.tsx
const [messageStreamingStatus, setMessageStreamingStatus] = useState<StreamingStatus>({});

// Set to true when streaming starts (line 147)
setMessageStreamingStatus(prev => ({ ...prev, [messageId]: true }));

// Set to false when streaming completes (line 184)
setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));
```

**Usage**: Used in conditional rendering to hide sources during streaming:
```typescript
{!messageStreamingStatus[message.id] && messageSources[message.id] && (
  <SourcesSection sources={messageSources[message.id]} />
)}
```

---

### 3. ExpandedInfoMap

**Purpose**: Track UI state for which message details sections are currently expanded.

**Structure** (TypeScript):
```typescript
interface ExpandedInfoMap {
  [messageId: string]: boolean;
}
```

**State Transitions**:
```
undefined → true/false  : First click toggles from undefined to opposite of current (defaults to false)
true → false            : User collapses the details section
false → true            : User expands the details section
```

**Validation Rules**:
- Key: Must be valid message ID (string)
- Value: Boolean only (true = expanded, false = collapsed)
- Default: Undefined (treated as false/collapsed)

**Lifecycle**:
- **Created**: On first user click of details toggle
- **Updated**: On each subsequent click (toggles value)
- **Persisted**: No (ephemeral, lost on page refresh)
- **Cleaned up**: When component unmounts (automatic React cleanup)

**Implementation Pattern**:
```typescript
const [expandedInfo, setExpandedInfo] = useState<ExpandedInfoMap>({});

const toggleInfo = (messageId: string) => {
  setExpandedInfo(prev => ({
    ...prev,
    [messageId]: !prev[messageId]
  }));
};

// Usage in JSX
<details open={expandedInfo[message.id]} onClick={() => toggleInfo(message.id)}>
  <summary>詳細資訊</summary>
  {/* metadata content */}
</details>
```

---

### 4. SearchResult (Modified)

**Purpose**: Add explicit `document_id` field for reliable document preview functionality.

**Current Structure** (from types):
```typescript
interface SearchResult {
  document_id: string;     // ADD THIS: Unique document identifier
  document_name: string;   // Existing: Display name
  content: string;         // Existing: Chunk content
  score: number;           // Existing: Relevance score
  file_url?: string;       // Existing: File URL (may be incorrect/incomplete)
  doc_type?: string;       // Existing: Document type
}
```

**Modifications**:
- **Add field**: `document_id: string` (required, non-empty)
- **Deprecate field**: `file_url` (keep for backward compatibility, but don't use for preview)

**Validation Rules**:
- `document_id`: MUST be non-empty string, MUST exist in backend storage
- Other fields: No changes to existing validation

**Backend Impact**:
- Backend already returns `document_id` in search results (verify in SearchResult schema)
- If not present, needs to be added to `rag.search()` return value

**Frontend Changes**:
```typescript
// OLD (incorrect)
<SourcePreview fileUrl={source.file_url} documentName={source.document_name} />

// NEW (correct)
<SourcePreview documentId={source.document_id} documentName={source.document_name} />
```

---

## Entity Relationships

```
Message (1) ─── (0..1) MessageMetadata
   │                      ↓
   │                   TokenUsage
   │
   ├─── (0..1) StreamingStatus [boolean]
   │
   ├─── (0..1) ExpandedInfoMap [boolean]
   │
   └─── (0..*) SearchResult
                   ↓
              document_id → Document (in backend storage)
```

**Key Relationships**:
1. Each assistant message MAY have metadata (only if response completed successfully)
2. Each assistant message HAS streaming status (boolean tracking)
3. Each assistant message MAY have expanded state (only after user interaction)
4. Each assistant message MAY have multiple search results (sources)
5. Each search result MUST reference a valid document via `document_id`

---

## Data Flow Diagrams

### Metadata Flow

```
Backend: OpenAI API
   │ (streaming + usage)
   ↓
Backend: chat.py (/api/chat/stream)
   │ {"type": "metadata", "data": {...}}
   ↓
Frontend: SSE Event Handler (ChatWindow.tsx)
   │ Parse metadata from SSE
   ↓
Frontend: messageMetadata state
   │ [messageId]: { model, duration_ms, tokens }
   ↓
Frontend: Details Section UI
   │ Display in collapsible section
   ↓
User: Views metadata
```

### Source Display Flow

```
User: Sends query
   ↓
Backend: Returns sources FIRST
   │ {"type": "sources", "data": [...]}
   ↓
Frontend: messageSources state
   │ Store but DON'T display yet
   ↓
Backend: Streams content chunks
   │ {"type": "content", "data": "..."}
   ↓
Frontend: messageStreamingStatus[id] = true
   │ Sources hidden during streaming
   ↓
Backend: Sends done event
   │ {"type": "done"}
   ↓
Frontend: messageStreamingStatus[id] = false
   │ Triggers re-render
   ↓
Frontend: Conditional render sources
   │ if (!messageStreamingStatus[id] && sources)
   ↓
User: Sees sources below completed response
```

### Document Preview Flow

```
User: Clicks "預覽原檔" button
   ↓
Frontend: SourcePreview component
   │ Constructs URL: /api/kb/documents/{documentId}/file
   ↓
Frontend: Opens in new tab
   │ window.open(fullUrl, '_blank')
   ↓
Backend: kb.py:145 get_document_file(document_id)
   │ Validates document_id
   │ Retrieves file from storage
   ↓
Backend: FileResponse
   │ Returns file with correct headers
   ↓
Browser: Displays/downloads file
```

---

## State Persistence

| Entity | Persistence | Rationale |
|--------|-------------|-----------|
| MessageMetadata | No (ephemeral) | Performance data, not critical to persist |
| StreamingStatus | No (ephemeral) | Streaming always complete on reload |
| ExpandedInfoMap | No (ephemeral) | UI preference, not worth complexity to save |
| Message (existing) | Yes (Zustand store) | Core chat data, already persisted |
| SearchResult (existing) | Yes (in message context) | Source citations, already persisted |

**Rationale for Non-Persistence**:
- All three new entities are UI/transient state
- Adds no value to persist (streaming always done on reload, metadata not critical)
- Reduces complexity and potential bugs
- Fast enough to regenerate on demand

---

## Validation Rules Summary

### Backend Validation (Python/Pydantic)

```python
# In backend/app/models/schemas.py or similar

class TokenUsage(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

class MessageMetadataSchema(BaseModel):
    model: str = Field(min_length=1, max_length=50)
    duration_ms: int = Field(ge=0)
    tokens: Optional[TokenUsage] = None

class SearchResult(BaseModel):
    document_id: str = Field(min_length=1)  # ADD THIS
    document_name: str
    content: str
    score: float
    file_url: Optional[str] = None  # Deprecated
    doc_type: Optional[str] = None
```

### Frontend Validation (TypeScript)

```typescript
// Runtime validation in SSE handler
if (data.type === 'metadata' && data.data) {
  const metadata = data.data as MessageMetadata;

  // Validate required fields
  if (!metadata.model || typeof metadata.duration_ms !== 'number') {
    console.error('Invalid metadata received:', metadata);
    return; // Skip invalid metadata
  }

  // Validate tokens if present
  if (metadata.tokens !== null) {
    if (typeof metadata.tokens.total_tokens !== 'number' ||
        metadata.tokens.total_tokens < 0) {
      console.error('Invalid token usage:', metadata.tokens);
      metadata.tokens = null; // Nullify invalid tokens
    }
  }

  setMessageMetadata(prev => ({
    ...prev,
    [messageId]: metadata,
  }));
}
```

---

## Migration Considerations

**No Database Migrations Required**: All new entities are frontend-only state.

**Backward Compatibility**:
- Existing messages without metadata: Display message without details section
- Existing SearchResults without `document_id`: Disable preview button or show error
- Graceful degradation: If metadata missing, hide details section entirely

**Rollback Safety**:
- No backend schema changes required
- Frontend changes are additive (don't break existing functionality)
- Can deploy and rollback without data loss

---

## Performance Implications

### Memory

- **MessageMetadata**: ~200 bytes per message (negligible)
- **StreamingStatus**: ~50 bytes per message (boolean + key)
- **ExpandedInfoMap**: ~50 bytes per message
- **Total overhead**: ~300 bytes per message × 100 messages = 30KB (acceptable)

### Computation

- State updates: O(1) - direct object key access
- Conditional rendering: O(1) - simple boolean check
- No expensive operations introduced

### Network

- Metadata payload: ~150 bytes per response (already transmitted)
- No additional API calls required
- No impact on existing chat performance

---

## Next Steps

With data model defined:
1. Generate API contracts showing SSE event schema
2. Define component interfaces for type safety
3. Create implementation tasks based on entity definitions
