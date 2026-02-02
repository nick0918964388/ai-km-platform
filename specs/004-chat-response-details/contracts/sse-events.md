# SSE Event Contract: Chat Streaming API

**Endpoint**: `POST /api/chat/stream`
**Protocol**: Server-Sent Events (SSE)
**Feature**: 004-chat-response-details

## Overview

This document defines the contract for Server-Sent Events emitted during chat streaming responses. The streaming endpoint returns multiple event types in a specific order to provide real-time response updates and metadata.

---

## Event Ordering

Events MUST be emitted in the following order:

```
1. sources     (once, at start)
2. content     (multiple, as response streams)
3. metadata    (once, at end)
4. done        (once, after metadata)

OR (on error):

1. sources     (once, at start)
2. error       (once, on failure)
```

---

## Event Format

All SSE events follow this structure:

```
data: <JSON_PAYLOAD>\n\n
```

Where `<JSON_PAYLOAD>` is a JSON object with:

```typescript
{
  type: "sources" | "content" | "metadata" | "done" | "error";
  data?: any;  // Optional, depends on type
}
```

---

## Event Type: `sources`

**Purpose**: Provide source documents that informed the AI response.

**When Emitted**: First event in the stream, before any content.

**Frequency**: Once per request.

**Payload Structure**:

```typescript
{
  type: "sources",
  data: SearchResult[]
}

interface SearchResult {
  document_id: string;        // Unique document identifier (REQUIRED)
  document_name: string;      // Human-readable document name
  content: string;            // Chunk content used for response
  score: number;              // Relevance score (0-1)
  file_url?: string;          // Deprecated: use document_id for preview
  doc_type?: string;          // Document type (e.g., "pdf", "image")
}
```

**Example**:

```json
data: {"type":"sources","data":[{"document_id":"doc_123","document_name":"EMU800維修手冊.pdf","content":"空氣彈簧更換步驟...","score":0.89,"doc_type":"pdf"},{"document_id":"doc_456","document_name":"煞車系統檢查.pdf","content":"制動缸檢查項目...","score":0.76,"doc_type":"pdf"}]}
```

**Validation Rules**:
- `data` MUST be an array (may be empty if no sources found)
- Each `SearchResult` MUST include `document_id`, `document_name`, `content`, `score`
- `score` MUST be a number between 0 and 1
- `document_id` MUST reference a valid document in the system

**Client Handling**:
- Store sources in state immediately upon receipt
- DO NOT display sources until receiving `done` event
- If `data` is empty array, do not render sources section

---

## Event Type: `content`

**Purpose**: Stream AI response text character-by-character or in chunks.

**When Emitted**: Continuously during response generation, after `sources` event.

**Frequency**: Multiple times per request (varies by response length).

**Payload Structure**:

```typescript
{
  type: "content",
  data: string  // Text chunk (may be single character or multiple)
}
```

**Example**:

```json
data: {"type":"content","data":"根據"}

data: {"type":"content","data":"維修手冊"}

data: {"type":"content","data":"，空氣"}

data: {"type":"content","data":"彈簧"}
```

**Validation Rules**:
- `data` MUST be a string (may be empty for heartbeat)
- Chunks MUST be appended in order to form complete response
- No guarantees about chunk size (may vary from 1 character to entire sentence)

**Client Handling**:
- Append each chunk to cumulative message content
- Update message display in real-time
- Continue until receiving `metadata` or `error` event

---

## Event Type: `metadata`

**Purpose**: Provide response metadata including model, duration, and token usage.

**When Emitted**: After all `content` events, before `done` event.

**Frequency**: Once per request.

**Payload Structure**:

```typescript
{
  type: "metadata",
  data: MessageMetadata
}

interface MessageMetadata {
  model: string;              // AI model used (e.g., "gpt-4o")
  duration_ms: number;        // Total response time in milliseconds
  tokens: TokenUsage | null;  // Token consumption, null if unavailable
}

interface TokenUsage {
  prompt_tokens: number;      // Tokens in the prompt
  completion_tokens: number;  // Tokens in the completion
  total_tokens: number;       // Sum of prompt + completion
}
```

**Example**:

```json
data: {"type":"metadata","data":{"model":"gpt-4o","duration_ms":3245,"tokens":{"prompt_tokens":1523,"completion_tokens":387,"total_tokens":1910}}}
```

**Example (tokens unavailable)**:

```json
data: {"type":"metadata","data":{"model":"gpt-4o","duration_ms":2981,"tokens":null}}
```

**Validation Rules**:
- `model` MUST be non-empty string, max 50 characters
- `duration_ms` MUST be non-negative integer (>= 0)
- `tokens` MAY be null if OpenAI API doesn't return usage data
- If `tokens` is not null, all three sub-fields MUST be present and non-negative

**Client Handling**:
- Store metadata in separate state keyed by message ID
- Render in collapsible details section below message
- If `tokens` is null, display "N/A" or hide token section
- Calculate duration in seconds for display: `duration_ms / 1000`

---

## Event Type: `done`

**Purpose**: Signal that streaming has completed successfully.

**When Emitted**: After `metadata` event, as final event in successful stream.

**Frequency**: Once per request (only on success).

**Payload Structure**:

```typescript
{
  type: "done"
  // No data field
}
```

**Example**:

```json
data: {"type":"done"}
```

**Validation Rules**:
- MUST be the final event in a successful stream
- MUST have no `data` field (or `data` is omitted)

**Client Handling**:
- Set `messageStreamingStatus[messageId] = false`
- Trigger display of source documents
- Mark loading state as complete
- No further events expected for this request

---

## Event Type: `error`

**Purpose**: Communicate errors that occur during streaming.

**When Emitted**: When an exception or error occurs during response generation.

**Frequency**: Once per request (only on error, replaces `content`/`metadata`/`done`).

**Payload Structure**:

```typescript
{
  type: "error",
  data: string  // Human-readable error message (Traditional Chinese)
}
```

**Example**:

```json
data: {"type":"error","data":"生成回答時發生錯誤: OpenAI API rate limit exceeded"}
```

**Validation Rules**:
- `data` MUST be a non-empty string
- Error message SHOULD be in Traditional Chinese for user-facing display
- Error message MUST NOT contain sensitive information (API keys, stack traces)

**Client Handling**:
- Display error message to user (do not show raw error)
- Set `messageStreamingStatus[messageId] = false`
- Optionally: Fall back to simulated response or retry logic
- Mark loading state as complete

---

## Complete Stream Examples

### Successful Stream

```
data: {"type":"sources","data":[{"document_id":"doc_123","document_name":"維修手冊.pdf","content":"...","score":0.89}]}

data: {"type":"content","data":"根據"}

data: {"type":"content","data":"維修手冊"}

data: {"type":"content","data":"的說明"}

data: {"type":"metadata","data":{"model":"gpt-4o","duration_ms":2500,"tokens":{"prompt_tokens":500,"completion_tokens":150,"total_tokens":650}}}

data: {"type":"done"}

```

### Error Stream

```
data: {"type":"sources","data":[{"document_id":"doc_123","document_name":"維修手冊.pdf","content":"...","score":0.89}]}

data: {"type":"error","data":"生成回答時發生錯誤: OpenAI API connection timeout"}

```

### No Sources Found

```
data: {"type":"sources","data":[]}

data: {"type":"content","data":"找不到相關的知識庫內容。請上傳相關文件後再試。"}

data: {"type":"metadata","data":{"model":"gpt-4o","duration_ms":150,"tokens":null}}

data: {"type":"done"}

```

---

## Backend Implementation Reference

**File**: `backend/app/routers/chat.py`

**Function**: `chat_stream(request: ChatRequest)`

Key implementation points:
- Line 53-62: Search and send sources first
- Line 69-78: Stream content chunks with usage tracking
- Line 80-88: Calculate duration and send metadata
- Line 91: Send done signal
- Line 94: Error handling with error event

---

## Frontend Implementation Reference

**File**: `frontend/src/components/chat/ChatWindow.tsx`

**Function**: `handleSend()` SSE parsing logic

Key implementation points:
- Line 170-174: Handle sources event
- Line 175-177: Handle content event
- Line 178-182: Handle metadata event
- Line 183-184: Handle done event
- Line 185-188: Handle error event

---

## Error Handling Matrix

| Scenario | Backend Behavior | Client Behavior |
|----------|------------------|-----------------|
| No sources found | Send empty `sources` array, continue with warning message | Display warning, no sources section |
| OpenAI API error | Send `error` event with message | Display error, show fallback response |
| Token usage unavailable | Send `metadata` with `tokens: null` | Display metadata without token section |
| Network disconnect mid-stream | Stream terminates | Detect incomplete stream, show partial response |
| Invalid JSON in SSE | N/A (server guarantees valid JSON) | Try-catch parse errors, log warning |

---

## Breaking Changes

**None**. This contract describes the existing API behavior with enhanced metadata support.

**Additions**:
- `document_id` field in `SearchResult` (additive, backward compatible)
- Explicit `tokens: null` handling (clarification, already supported)

**Deprecations**:
- `file_url` in `SearchResult` (deprecated in favor of `document_id`, but still present)

---

## Testing Checklist

- [ ] Verify `sources` always sent first
- [ ] Verify `content` events stream in order
- [ ] Verify `metadata` sent before `done`
- [ ] Verify `done` is final event on success
- [ ] Verify `error` replaces normal flow on failure
- [ ] Verify `tokens` can be null without breaking client
- [ ] Verify empty `sources` array handled gracefully
- [ ] Verify malformed JSON caught and logged
- [ ] Verify network interruption handled
- [ ] Verify all events parseable by frontend SSE handler

---

## Version History

- **v1.0** (2026-02-02): Initial contract definition for 004-chat-response-details feature
