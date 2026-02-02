# Component Interface Contracts

**Feature**: 004-chat-response-details
**Date**: 2026-02-02
**Purpose**: Define TypeScript interfaces and component props for type safety

---

## Overview

This document defines the TypeScript interfaces and component contracts for the chat response details feature. All interfaces follow strict TypeScript typing with explicit null handling.

---

## Shared Types

### MessageMetadata

**Location**: `frontend/src/types/index.ts`

```typescript
/**
 * Metadata about an AI response, including model info, timing, and token usage.
 * Displayed in the collapsible details section below each assistant message.
 */
export interface MessageMetadata {
  /** AI model used to generate the response (e.g., "gpt-4o") */
  model: string;

  /** Total response generation time in milliseconds */
  duration_ms: number;

  /** Token usage details, null if unavailable from API */
  tokens: TokenUsage | null;
}

/**
 * Token consumption breakdown from OpenAI API.
 */
export interface TokenUsage {
  /** Number of tokens in the prompt */
  prompt_tokens: number;

  /** Number of tokens in the completion */
  completion_tokens: number;

  /** Total tokens used (prompt + completion) */
  total_tokens: number;
}
```

**Usage Example**:
```typescript
const metadata: MessageMetadata = {
  model: "gpt-4o",
  duration_ms: 3245,
  tokens: {
    prompt_tokens: 1523,
    completion_tokens: 387,
    total_tokens: 1910,
  },
};

// With unavailable tokens
const metadataNoTokens: MessageMetadata = {
  model: "gpt-4o",
  duration_ms: 2981,
  tokens: null,
};
```

---

### MessageMetadataMap

**Location**: `frontend/src/components/chat/ChatWindow.tsx`

```typescript
/**
 * Map of message IDs to their metadata.
 * Used to store metadata for all messages in the current conversation.
 */
interface MessageMetadataMap {
  [messageId: string]: MessageMetadata;
}
```

**Usage Example**:
```typescript
const [messageMetadata, setMessageMetadata] = useState<MessageMetadataMap>({});

// Adding metadata for a message
setMessageMetadata(prev => ({
  ...prev,
  [messageId]: {
    model: "gpt-4o",
    duration_ms: 3245,
    tokens: { prompt_tokens: 1523, completion_tokens: 387, total_tokens: 1910 },
  },
}));

// Retrieving metadata
const metadata = messageMetadata[messageId];
if (metadata) {
  console.log(`Response took ${metadata.duration_ms}ms`);
}
```

---

### StreamingStatus

**Location**: `frontend/src/components/chat/ChatWindow.tsx`

```typescript
/**
 * Map of message IDs to their streaming status.
 * true = currently streaming, false = streaming complete.
 * Used to control when source documents are displayed.
 */
interface StreamingStatus {
  [messageId: string]: boolean;
}
```

**Usage Example**:
```typescript
const [messageStreamingStatus, setMessageStreamingStatus] = useState<StreamingStatus>({});

// Mark as streaming when response starts
setMessageStreamingStatus(prev => ({ ...prev, [messageId]: true }));

// Mark as complete when done event received
setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));

// Check if streaming in render
const isStreaming = messageStreamingStatus[message.id];
if (!isStreaming && sources) {
  // Display sources
}
```

---

### ExpandedInfoMap

**Location**: `frontend/src/components/chat/ChatWindow.tsx`

```typescript
/**
 * Map of message IDs to details section expanded state.
 * true = expanded, false/undefined = collapsed.
 * Controls visibility of metadata details section.
 */
interface ExpandedInfoMap {
  [messageId: string]: boolean;
}
```

**Usage Example**:
```typescript
const [expandedInfo, setExpandedInfo] = useState<ExpandedInfoMap>({});

// Toggle expanded state
const toggleInfo = (messageId: string) => {
  setExpandedInfo(prev => ({
    ...prev,
    [messageId]: !prev[messageId],
  }));
};

// Use in render
const isExpanded = expandedInfo[message.id] || false;
```

---

### SearchResult (Modified)

**Location**: `frontend/src/types/index.ts`

```typescript
/**
 * A single search result from the RAG knowledge base.
 * Represents a document chunk relevant to the user's query.
 */
export interface SearchResult {
  /** Unique identifier for the document (REQUIRED for preview) */
  document_id: string;

  /** Human-readable document name */
  document_name: string;

  /** Content of the document chunk */
  content: string;

  /** Relevance score from vector search (0-1) */
  score: number;

  /** @deprecated Use document_id for preview instead */
  file_url?: string | null;

  /** Document type (e.g., "pdf", "image", "word") */
  doc_type?: string;
}
```

**Migration Note**:
- **Old code** (incorrect): `<SourcePreview fileUrl={source.file_url} ... />`
- **New code** (correct): `<SourcePreview documentId={source.document_id} ... />`

---

## Component Interfaces

### SourcePreview Props

**Location**: `frontend/src/components/chat/SourcePreview.tsx`

```typescript
interface SourcePreviewProps {
  /** Unique document identifier for backend API */
  documentId: string | null | undefined;

  /** Human-readable document name for display */
  documentName: string;
}

/**
 * SourcePreview component displays a button to preview source documents.
 *
 * @param documentId - Document ID to fetch from backend (required for preview)
 * @param documentName - Display name shown to user
 *
 * @example
 * <SourcePreview documentId="doc_123" documentName="EMU800維修手冊.pdf" />
 */
export default function SourcePreview({ documentId, documentName }: SourcePreviewProps) {
  // Implementation
}
```

**Validation**:
- If `documentId` is `null` or `undefined`, button should be disabled or show error
- `documentName` should always be non-empty (display "Unknown" if missing)

**Behavior**:
```typescript
const handlePreview = () => {
  if (!documentId) {
    alert('無法預覽：缺少文件ID');
    return;
  }

  const fullUrl = `${API_URL}/api/kb/documents/${documentId}/file`;
  window.open(fullUrl, '_blank');
};
```

---

### MessageSources Map

**Location**: `frontend/src/components/chat/ChatWindow.tsx`

```typescript
/**
 * Map of message IDs to their source documents.
 * Stores all source documents retrieved for each message.
 */
interface MessageSources {
  [messageId: string]: SearchResult[];
}
```

**Usage Example**:
```typescript
const [messageSources, setMessageSources] = useState<MessageSources>({});

// Store sources from SSE
if (data.type === 'sources' && data.data?.length > 0) {
  setMessageSources(prev => ({
    ...prev,
    [messageId]: data.data,
  }));
}

// Retrieve sources for rendering
const sources = messageSources[message.id];
```

---

## SSE Event Types

### SSEEvent

**Location**: `frontend/src/components/chat/ChatWindow.tsx` (inline type)

```typescript
/**
 * Server-Sent Event structure from /api/chat/stream.
 * All events follow this base structure with type-specific data.
 */
interface SSEEvent {
  type: 'sources' | 'content' | 'metadata' | 'done' | 'error';
  data?: any;
}

/**
 * Type guards for SSE events
 */
type SourcesEvent = SSEEvent & {
  type: 'sources';
  data: SearchResult[];
};

type ContentEvent = SSEEvent & {
  type: 'content';
  data: string;
};

type MetadataEvent = SSEEvent & {
  type: 'metadata';
  data: MessageMetadata;
};

type DoneEvent = SSEEvent & {
  type: 'done';
  data?: never;
};

type ErrorEvent = SSEEvent & {
  type: 'error';
  data: string;
};
```

**Usage Example**:
```typescript
const line = 'data: {"type":"metadata","data":{...}}';
const data = JSON.parse(line.slice(6)) as SSEEvent;

if (data.type === 'sources' && data.data?.length > 0) {
  const sources = data.data as SearchResult[];
  // Handle sources
} else if (data.type === 'metadata' && data.data) {
  const metadata = data.data as MessageMetadata;
  // Handle metadata
}
```

---

## State Management Types

### ChatWindow State

**Complete state interface for ChatWindow component**:

```typescript
interface ChatWindowState {
  // Input state
  input: string;
  isRecording: boolean;

  // Loading states
  isLoading: boolean;
  isStreaming: boolean;

  // Message-specific states
  messageSources: MessageSources;
  messageMetadata: MessageMetadataMap;
  messageStreamingStatus: StreamingStatus;
  expandedInfo: ExpandedInfoMap;

  // UI state
  voiceSupported: boolean;
}

// State setters
type SetState<T> = React.Dispatch<React.SetStateAction<T>>;

interface ChatWindowSetters {
  setInput: SetState<string>;
  setIsRecording: SetState<boolean>;
  setIsLoading: SetState<boolean>;
  setIsStreaming: SetState<boolean>;
  setMessageSources: SetState<MessageSources>;
  setMessageMetadata: SetState<MessageMetadataMap>;
  setMessageStreamingStatus: SetState<StreamingStatus>;
  setExpandedInfo: SetState<ExpandedInfoMap>;
  setVoiceSupported: SetState<boolean>;
}
```

---

## Validation Utilities

### Type Guards

```typescript
/**
 * Type guard to check if metadata has valid token usage.
 * Use this before accessing token fields.
 */
export function hasTokenUsage(metadata: MessageMetadata): metadata is MessageMetadata & { tokens: TokenUsage } {
  return metadata.tokens !== null &&
         typeof metadata.tokens.total_tokens === 'number' &&
         metadata.tokens.total_tokens >= 0;
}

/**
 * Type guard to check if SearchResult has valid document_id.
 * Use this before attempting document preview.
 */
export function hasDocumentId(source: SearchResult): source is SearchResult & { document_id: string } {
  return typeof source.document_id === 'string' &&
         source.document_id.length > 0;
}
```

**Usage Example**:
```typescript
// Check token usage before rendering
if (hasTokenUsage(metadata)) {
  return <div>Tokens: {metadata.tokens.total_tokens}</div>;
} else {
  return <div>Token usage not available</div>;
}

// Check document_id before preview
const handlePreview = (source: SearchResult) => {
  if (!hasDocumentId(source)) {
    alert('無法預覽：缺少文件ID');
    return;
  }
  window.open(`${API_URL}/api/kb/documents/${source.document_id}/file`, '_blank');
};
```

---

## Error Handling Types

### PreviewError

```typescript
/**
 * Error states for document preview functionality.
 */
type PreviewError =
  | 'missing_document_id'
  | 'document_not_found'
  | 'file_not_exists'
  | 'network_error'
  | 'unknown_error';

/**
 * Get user-friendly error message for preview errors.
 */
function getPreviewErrorMessage(error: PreviewError): string {
  switch (error) {
    case 'missing_document_id':
      return '無法預覽：缺少文件識別碼';
    case 'document_not_found':
      return '找不到原始檔案';
    case 'file_not_exists':
      return '檔案不存在';
    case 'network_error':
      return '網路錯誤：無法載入預覽';
    case 'unknown_error':
    default:
      return '預覽時發生未知錯誤';
  }
}
```

---

## Null Safety Patterns

### Safe Metadata Access

```typescript
/**
 * Safely access metadata with fallback values.
 */
function getMetadataDisplay(messageId: string, metadata: MessageMetadataMap) {
  const data = metadata[messageId];

  if (!data) {
    return null; // No metadata available, don't render section
  }

  return {
    model: data.model || 'Unknown',
    duration: data.duration_ms ? `${(data.duration_ms / 1000).toFixed(2)}秒` : 'N/A',
    tokens: data.tokens ? `${data.tokens.total_tokens} tokens` : 'N/A',
  };
}
```

### Safe Source Rendering

```typescript
/**
 * Safely render sources with streaming check.
 */
function renderSources(
  messageId: string,
  sources: MessageSources,
  streamingStatus: StreamingStatus
): JSX.Element | null {
  const isStreaming = streamingStatus[messageId];
  const messageSources = sources[messageId];

  // Don't render if still streaming or no sources
  if (isStreaming || !messageSources || messageSources.length === 0) {
    return null;
  }

  return (
    <div className="sources-section">
      {messageSources.map((source, idx) => (
        <SourcePreview
          key={idx}
          documentId={source.document_id}
          documentName={source.document_name}
        />
      ))}
    </div>
  );
}
```

---

## Testing Interfaces

### Mock Data

```typescript
/**
 * Mock metadata for testing.
 */
export const mockMetadata: MessageMetadata = {
  model: 'gpt-4o',
  duration_ms: 3245,
  tokens: {
    prompt_tokens: 1523,
    completion_tokens: 387,
    total_tokens: 1910,
  },
};

/**
 * Mock metadata without token usage.
 */
export const mockMetadataNoTokens: MessageMetadata = {
  model: 'gpt-4o',
  duration_ms: 2981,
  tokens: null,
};

/**
 * Mock search result.
 */
export const mockSearchResult: SearchResult = {
  document_id: 'doc_123',
  document_name: 'EMU800維修手冊.pdf',
  content: '空氣彈簧更換步驟...',
  score: 0.89,
  doc_type: 'pdf',
};
```

---

## Version History

- **v1.0** (2026-02-02): Initial component interface definitions for 004-chat-response-details
