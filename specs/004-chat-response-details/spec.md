# Feature Specification: Chat Response Details and Source Display Fixes

**Feature Branch**: `004-chat-response-details`
**Created**: 2026-02-02
**Status**: Draft
**Input**: User description: "AI問答回覆詳細資訊與來源文件顯示修正"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Response Metadata (Priority: P1)

After receiving an AI response, users want to understand the technical details behind the response including which AI model was used, how long it took to generate, and how many tokens were consumed. This information helps users evaluate response quality and understand system performance.

**Why this priority**: Core feature that provides transparency and trust. Users can validate whether responses meet their performance expectations and understand resource consumption patterns.

**Independent Test**: Can be fully tested by sending any chat message and verifying that the collapsible details section appears below the AI response with accurate metadata.

**Acceptance Scenarios**:

1. **Given** a user has sent a chat message and received an AI response, **When** the response is fully displayed, **Then** a collapsible "詳細資訊" (Details) section appears below the response in a collapsed state
2. **Given** the details section is collapsed, **When** the user clicks on it, **Then** it expands to show: model name, total response duration, and token usage
3. **Given** the details section is expanded, **When** the user clicks on it again, **Then** it collapses to hide the metadata

---

### User Story 2 - Source Documents After Complete Response (Priority: P1)

Users need to see source documents only after the AI response text has finished streaming. Currently, source documents appear too early during the streaming process, which creates a jarring user experience and makes it difficult to follow the response.

**Why this priority**: Critical UX fix that ensures users can read the complete response before being presented with source citations. This follows natural reading patterns and improves information comprehension.

**Independent Test**: Can be fully tested by sending a chat query and observing that source documents appear only after the last character of the streaming response is displayed.

**Acceptance Scenarios**:

1. **Given** a user sends a chat message, **When** the AI response is streaming character by character, **Then** source documents section remains hidden
2. **Given** the AI response streaming has completed, **When** the last character is displayed, **Then** the source documents section appears below the response
3. **Given** a response has no streaming (non-streaming fallback), **When** the response is displayed, **Then** source documents appear immediately with the response

---

### User Story 3 - Fix Document Preview (Priority: P2)

Users need to preview source documents by clicking the preview button, but currently encounter "undefined Internal Server Error" when attempting to open previews. This prevents users from verifying the original source material that informed the AI response.

**Why this priority**: Important for document verification and trust, but lower priority than the display timing issues since users can still see document names and the chat functionality works.

**Independent Test**: Can be fully tested by clicking any document preview button in the source documents section and verifying the preview modal opens successfully without errors.

**Acceptance Scenarios**:

1. **Given** a user sees source documents listed below an AI response, **When** they click the "預覽原檔" (Preview) button, **Then** the document preview modal opens successfully showing the document content
2. **Given** the preview button is clicked, **When** the backend receives the request, **Then** the correct document_id is passed in the API call
3. **Given** a document cannot be loaded, **When** the preview is attempted, **Then** a user-friendly error message is displayed instead of "undefined Internal Server Error"

---

### Edge Cases

- What happens when the AI response streams very quickly (< 1 second)? Source documents should still wait until streaming completes.
- What happens when streaming fails or times out? Source documents should appear with the fallback response.
- What happens when there are no source documents found for a query? The source documents section should not appear at all.
- What happens when token usage data is not available from the API? The details section should show "N/A" or hide the unavailable field.
- What happens when a user rapidly clicks the details section expand/collapse? The UI should handle rapid toggling smoothly without visual glitches.
- What happens when document_id is null or undefined? The preview button should be disabled or show an appropriate error message.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a collapsible details section below each AI assistant message
- **FR-002**: Details section MUST default to collapsed state when response is first displayed
- **FR-003**: Details section MUST show model name, total response duration (in seconds), and token usage when expanded
- **FR-004**: Details section MUST use a light gray background color and smaller font size than the main response text
- **FR-005**: System MUST delay displaying source documents until the streaming response has completely finished
- **FR-006**: System MUST track streaming completion state separately from loading state
- **FR-007**: Source documents section MUST only appear when streaming is complete AND sources exist
- **FR-008**: System MUST correctly pass document_id to the preview endpoint when preview button is clicked
- **FR-009**: Preview functionality MUST handle missing or invalid document_id gracefully with user-friendly error messages
- **FR-010**: System MUST capture and store response metadata (model, duration, tokens) during the chat API interaction
- **FR-011**: Collapsible details section MUST have clear visual affordances indicating it can be expanded/collapsed
- **FR-012**: System MUST maintain consistent styling with existing chat UI design patterns

### Key Entities

- **Response Metadata**: Contains model name (string), response duration (number in seconds), token usage (object with prompt_tokens, completion_tokens, total_tokens)
- **Message Sources**: Collection of source documents associated with a specific message, including document_id, document_name, and file_url
- **Streaming State**: Boolean flag tracking whether a message is currently streaming, separate from general loading state

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view response metadata within 1 click (expanding the details section) for any AI response
- **SC-002**: Source documents appear within 100ms after the last streamed character is displayed
- **SC-003**: 100% of document preview attempts with valid document_id successfully open the preview modal without errors
- **SC-004**: Users can toggle the details section expand/collapse state in under 0.3 seconds with smooth animation
- **SC-005**: Zero instances of "undefined Internal Server Error" when clicking document preview buttons with valid documents
- **SC-006**: Users can complete a full chat interaction (send query, read response, check details, preview source) without encountering errors
