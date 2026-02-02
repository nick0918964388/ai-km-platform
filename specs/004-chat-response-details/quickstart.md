# Quickstart Guide: Chat Response Details Implementation

**Feature**: 004-chat-response-details
**Branch**: `004-chat-response-details`
**Date**: 2026-02-02

## Overview

This guide helps developers quickly set up, implement, test, and verify the chat response details feature. Follow these steps in order for a smooth implementation process.

---

## Prerequisites

Before starting, ensure you have:

- [x] Branch `004-chat-response-details` checked out
- [x] Backend running on `http://localhost:8000`
- [x] Frontend running on `http://localhost:3000`
- [x] OpenAI API key configured in `.env`
- [x] At least one document uploaded to the knowledge base
- [x] Basic familiarity with:
  - React hooks (`useState`, `useEffect`)
  - Server-Sent Events (SSE)
  - TypeScript interfaces
  - IBM Carbon design system

---

## Quick Start (5 minutes)

### 1. Verify Current State

```bash
# Check you're on the right branch
git branch --show-current
# Should output: 004-chat-response-details

# Verify backend is running
curl http://localhost:8000/api/health || echo "Backend not running!"

# Verify frontend is running
curl http://localhost:3000 || echo "Frontend not running!"
```

### 2. Review Key Files

Before making changes, understand these files:

```bash
# Backend (metadata already captured)
cat backend/app/routers/chat.py | grep -A 10 "metadata"
cat backend/app/services/rag.py | grep -A 10 "stream_options"

# Frontend (streaming status already tracked)
cat frontend/src/components/chat/ChatWindow.tsx | grep -A 5 "messageStreamingStatus"

# Types (may need MessageMetadata added)
cat frontend/src/types/index.ts | grep -A 5 "interface"
```

### 3. Test Current Behavior

Open browser to `http://localhost:3000`:
1. Send a test query: "EMU800 空氣彈簧如何更換？"
2. Observe:
   - ❌ Sources appear immediately (too early)
   - ❌ No metadata displayed below response
   - ❌ Preview buttons may error with "undefined Internal Server Error"

---

## Implementation Steps

### Step 1: Add TypeScript Types (Frontend)

**File**: `frontend/src/types/index.ts`

```typescript
// Add these interfaces at the top of the file

export interface MessageMetadata {
  model: string;
  duration_ms: number;
  tokens: TokenUsage | null;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

// Modify SearchResult to add document_id
export interface SearchResult {
  document_id: string;  // ADD THIS LINE
  document_name: string;
  content: string;
  score: number;
  file_url?: string | null;
  doc_type?: string;
}
```

**Verify**:
```bash
grep "interface MessageMetadata" frontend/src/types/index.ts
# Should show the new interface
```

---

### Step 2: Delay Source Display Until Streaming Completes

**File**: `frontend/src/components/chat/ChatWindow.tsx`

**Find the sources rendering section** (around line 300-320) and wrap it with streaming check:

```typescript
{/* OLD CODE (sources shown immediately) */}
{messageSources[msg.id] && (
  <div className="sources-section">
    {/* ... */}
  </div>
)}

{/* NEW CODE (sources shown only after streaming completes) */}
{!messageStreamingStatus[msg.id] && messageSources[msg.id] && (
  <div className="sources-section">
    {/* ... */}
  </div>
)}
```

**Verify**:
```bash
grep "!messageStreamingStatus\[msg.id\] && messageSources" frontend/src/components/chat/ChatWindow.tsx
# Should show the updated condition
```

---

### Step 3: Add Details Section Below Each Response

**File**: `frontend/src/components/chat/ChatWindow.tsx`

**Add new state** at the top of the component (around line 52):

```typescript
const [expandedInfo, setExpandedInfo] = useState<ExpandedInfoMap>({});
```

**Add toggle function** (around line 90):

```typescript
const toggleInfo = (messageId: string) => {
  setExpandedInfo(prev => ({
    ...prev,
    [messageId]: !prev[messageId]
  }));
};
```

**Add details section in message rendering** (after message content, before sources):

```typescript
{/* Add this after the message content div */}
{msg.role === 'assistant' && messageMetadata[msg.id] && (
  <details
    className="message-details"
    open={expandedInfo[msg.id]}
    onClick={() => toggleInfo(msg.id)}
  >
    <summary>詳細資訊</summary>
    <div className="details-content">
      <div className="detail-item">
        <span className="detail-label">模型:</span>
        <span className="detail-value">{messageMetadata[msg.id].model}</span>
      </div>
      <div className="detail-item">
        <span className="detail-label">回應時間:</span>
        <span className="detail-value">
          {(messageMetadata[msg.id].duration_ms / 1000).toFixed(2)}秒
        </span>
      </div>
      {messageMetadata[msg.id].tokens && (
        <div className="detail-item">
          <span className="detail-label">Token 使用:</span>
          <span className="detail-value">
            {messageMetadata[msg.id].tokens!.total_tokens} tokens
            (輸入: {messageMetadata[msg.id].tokens!.prompt_tokens},
            輸出: {messageMetadata[msg.id].tokens!.completion_tokens})
          </span>
        </div>
      )}
    </div>
  </details>
)}
```

**Add CSS styling** at the bottom of the file (in existing `<style jsx>` block):

```css
.message-details {
  margin-top: 0.75rem;
  padding: 0.5rem;
  background-color: #f4f4f4;
  border-radius: 4px;
  font-size: 0.875rem;
  cursor: pointer;
}

.message-details summary {
  font-weight: 500;
  color: #0f62fe;
  user-select: none;
  list-style: none;
}

.message-details summary::-webkit-details-marker {
  display: none;
}

.message-details[open] summary {
  margin-bottom: 0.5rem;
}

.details-content {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-item {
  display: flex;
  gap: 0.5rem;
}

.detail-label {
  font-weight: 500;
  color: #525252;
}

.detail-value {
  color: #161616;
}
```

---

### Step 4: Fix Document Preview

**File**: `frontend/src/components/chat/SourcePreview.tsx`

**Replace entire component** with correct implementation:

```typescript
'use client';

import { Document } from '@carbon/icons-react';
import { API_URL } from '@/lib/api';

interface SourcePreviewProps {
  documentId: string | null | undefined;
  documentName: string;
}

export default function SourcePreview({ documentId, documentName }: SourcePreviewProps) {
  const handlePreview = () => {
    if (!documentId) {
      alert('無法預覽：缺少文件識別碼');
      return;
    }

    const fullUrl = `${API_URL}/api/kb/documents/${documentId}/file`;
    window.open(fullUrl, '_blank');
  };

  if (!documentId) {
    return null; // Don't render button if no document_id
  }

  return (
    <button
      className="source-preview-btn"
      onClick={handlePreview}
      title={`預覽 ${documentName}`}
    >
      <Document size={14} />
      <span>預覽原檔</span>

      <style jsx>{`
        .source-preview-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.25rem 0.5rem;
          font-size: 0.75rem;
          color: var(--primary, #0f62fe);
          background: var(--bg-brand-light, #e5f0ff);
          border: 1px solid var(--primary, #0f62fe);
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.15s ease;
          white-space: nowrap;
        }

        .source-preview-btn:hover {
          background: var(--primary, #0f62fe);
          color: white;
        }

        .source-preview-btn:active {
          transform: scale(0.98);
        }
      `}</style>
    </button>
  );
}
```

**Update SourcePreview usage** in `ChatWindow.tsx` (around line 310):

```typescript
{/* OLD */}
<SourcePreview fileUrl={source.file_url} documentName={source.document_name} />

{/* NEW */}
<SourcePreview documentId={source.document_id} documentName={source.document_name} />
```

---

## Verification Checklist

### Manual Testing

Open `http://localhost:3000` and perform these tests:

- [ ] **Test 1: Response Metadata**
  1. Send query: "EMU800 維修步驟"
  2. Wait for response to complete
  3. Verify "詳細資訊" section appears below response (collapsed)
  4. Click to expand
  5. Verify shows: model, response time, token usage
  6. Click to collapse
  7. Verify collapses smoothly

- [ ] **Test 2: Source Timing**
  1. Send query: "空氣彈簧更換"
  2. Observe streaming response
  3. Verify sources **NOT** visible during streaming
  4. Wait for response to finish
  5. Verify sources appear immediately after last character

- [ ] **Test 3: Document Preview**
  1. Send query that returns sources
  2. Wait for sources to appear
  3. Click "預覽原檔" button
  4. Verify document opens in new tab (no error)
  5. Verify document displays correctly

- [ ] **Test 4: Edge Cases**
  1. Send query with no results
  2. Verify no sources section, no errors
  3. Send query with very fast response (<1s)
  4. Verify sources still wait for streaming complete
  5. Verify metadata shows correct sub-second time

### Browser Console Checks

```javascript
// No errors should appear
// No warnings about missing document_id
// No "undefined Internal Server Error"
```

### Performance Verification

- [ ] Source display after streaming: <100ms (visually instant)
- [ ] Details toggle animation: <300ms (smooth)
- [ ] No lag or jank when expanding/collapsing

---

## Troubleshooting

### Issue: Metadata not showing

**Symptom**: Details section never appears
**Causes**:
1. Backend not sending metadata event
2. Frontend not storing metadata in state
3. Type mismatch in SSE parsing

**Debug**:
```javascript
// Add in handleSend() SSE parsing (line 178)
console.log('Received metadata:', data.data);
console.log('Current messageMetadata state:', messageMetadata);
```

**Fix**: Verify backend sends `{"type": "metadata", "data": {...}}` event

---

### Issue: Sources still appear during streaming

**Symptom**: Sources flash before response finishes
**Causes**:
1. Missing `!messageStreamingStatus[msg.id]` condition
2. `messageStreamingStatus` not set to `true` initially

**Debug**:
```javascript
// Add in message rendering (line 300)
console.log('Streaming status:', messageStreamingStatus[msg.id]);
console.log('Has sources:', !!messageSources[msg.id]);
```

**Fix**: Ensure condition is `{!messageStreamingStatus[msg.id] && messageSources[msg.id] && ...}`

---

### Issue: Document preview shows error

**Symptom**: "undefined Internal Server Error" or "找不到原始檔案"
**Causes**:
1. `document_id` is undefined/null
2. Backend expects different parameter format
3. Document not in storage

**Debug**:
```javascript
// Add in SourcePreview.tsx handlePreview()
console.log('documentId:', documentId);
console.log('Constructed URL:', fullUrl);
```

**Fix**:
1. Verify `source.document_id` exists in SSE sources event
2. Check backend logs for actual error
3. Verify document uploaded successfully

---

### Issue: Tokens showing "null"

**Symptom**: Token usage says "N/A" or blank
**Causes**:
1. OpenAI API not returning usage (rate limit, error)
2. Backend not passing through token data

**This is expected behavior**: Tokens may be null if OpenAI doesn't provide usage data. Handle gracefully with conditional rendering.

---

## Development Workflow

### Iterative Development

```bash
# 1. Make changes to frontend
code frontend/src/components/chat/ChatWindow.tsx

# 2. Hot reload should pick up changes automatically
# If not, restart dev server:
cd frontend && npm run dev

# 3. Test in browser
open http://localhost:3000

# 4. Check browser console for errors
# 5. Repeat until satisfied
```

### Testing Cycle

```bash
# 1. Unit tests (if added)
cd frontend && npm test

# 2. Manual testing (follow checklist above)

# 3. Backend logs
docker-compose logs backend -f

# 4. Network inspection
# Open DevTools > Network > Filter by "stream"
# Verify SSE events in correct order
```

---

## Next Steps

After completing implementation:

1. **Run `/speckit.tasks`** to generate task breakdown
2. **Run `/speckit.implement`** to execute tasks automatically
3. **Create PR** following commit guidelines
4. **Add E2E tests** if available (optional)

---

## References

- **Spec**: [spec.md](./spec.md)
- **Plan**: [plan.md](./plan.md)
- **Research**: [research.md](./research.md)
- **Data Model**: [data-model.md](./data-model.md)
- **Contracts**: [contracts/](./contracts/)

---

## Support

If you encounter issues not covered here:

1. Check the spec for acceptance criteria
2. Review research.md for technical decisions
3. Check existing git issues on branch
4. Ask team for clarification

---

**Estimated Implementation Time**: 2-3 hours for experienced developer

**Complexity**: Low-Medium (mostly frontend state management)

**Risk Level**: Low (additive changes, backward compatible)
