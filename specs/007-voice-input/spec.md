# Feature Specification: Voice Input for Search

**Feature Branch**: `007-voice-input`
**Created**: 2026-02-03
**Status**: Draft
**Input**: User description: "為 AIKM 平台新增語音輸入功能：
1. 在搜尋框旁邊新增麥克風按鈕
2. 使用 VAD (Voice Activity Detection) 偵測說話停頓，自動分段
3. 每段語音送至 ASR API (https://voicemodel.nickai.cc/v1/audio/transcriptions) 辨識
4. 辨識結果即時填入搜尋框
5. 支援連續說話，多段結果會累加

技術規格：
- 前端使用 @ricky0123/vad-web 做 VAD
- ASR API 格式：POST multipart/form-data, file 欄位為音檔
- 回應格式：{ "text": "辨識結果" }"

## User Scenarios & Testing

### User Story 1 - Basic Voice Search Input (Priority: P1)

A user wants to search for documents by speaking instead of typing. They click the microphone button next to the search box, speak their query, and see the transcribed text appear in the search box automatically.

**Why this priority**: This is the core functionality that delivers the primary value proposition - enabling hands-free search. Without this, the feature has no purpose.

**Independent Test**: Can be fully tested by clicking the microphone button, speaking a simple query like "project report 2024", and verifying the text appears in the search box. Delivers immediate value for basic voice search.

**Acceptance Scenarios**:

1. **Given** the user is on the search page, **When** they click the microphone button, **Then** the button should indicate recording is active and the system should start listening for voice input
2. **Given** recording is active, **When** the user speaks a query and pauses, **Then** the spoken words should be transcribed and appear in the search box within 2 seconds
3. **Given** transcribed text appears in the search box, **When** the user reviews the text, **Then** it should accurately reflect what they spoke with reasonable accuracy (>85% word accuracy for clear speech)

---

### User Story 2 - Continuous Multi-Segment Speech (Priority: P2)

A user wants to speak a longer, more complex query in multiple segments. They start speaking, pause briefly to think, then continue speaking. The system should automatically detect pauses, transcribe each segment, and append the results to form a complete query.

**Why this priority**: Enables more natural speech patterns and longer queries, improving usability beyond simple short commands. Users don't need to speak in one continuous stream.

**Independent Test**: Can be tested by speaking "find all documents about" [pause 1-2 seconds] "machine learning projects" and verifying both segments are transcribed and concatenated in the search box.

**Acceptance Scenarios**:

1. **Given** the user is actively recording, **When** they pause speaking for 1-2 seconds, **Then** the system should automatically detect the pause and send that audio segment for transcription
2. **Given** a segment has been transcribed, **When** the user continues speaking after a pause, **Then** the new speech should be detected as a new segment and appended to the existing text
3. **Given** multiple segments have been transcribed, **When** the user reviews the search box, **Then** all segments should be concatenated with appropriate spacing to form a coherent query

---

### User Story 3 - Recording Control and Cancellation (Priority: P3)

A user wants to control the voice recording process. They should be able to manually stop recording when done, or cancel if they change their mind, without having to delete text manually.

**Why this priority**: Provides better user control and error recovery, but the feature is still usable without explicit stop/cancel controls (auto-detection handles most cases).

**Independent Test**: Can be tested by clicking the microphone button to start recording, then clicking it again to stop, or clicking a cancel button to discard the recording.

**Acceptance Scenarios**:

1. **Given** recording is active, **When** the user clicks the microphone button again, **Then** recording should stop and any pending audio should be transcribed
2. **Given** recording is active, **When** the user clicks a cancel button, **Then** recording should stop and any transcribed text should be discarded from the search box
3. **Given** the user has stopped recording, **When** they want to add more voice input, **Then** they can click the microphone button again to resume recording and append to existing text

---

### Edge Cases

- What happens when the user's microphone permissions are denied or unavailable?
- How does the system handle background noise or unclear speech that cannot be transcribed?
- What happens if the ASR API is unavailable or returns an error?
- How does the system handle very long continuous speech (>30 seconds without pauses)?
- What happens when the user speaks in a language not supported by the ASR service?
- How does the system handle rapid consecutive speech segments without clear pauses?
- What happens if the user navigates away from the page while recording is active?

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a microphone button adjacent to the search input field that is clearly visible and accessible
- **FR-002**: System MUST indicate recording status visually (e.g., animated icon, color change) when the microphone button is activated
- **FR-003**: System MUST request and obtain microphone permissions from the user's browser before accessing audio input
- **FR-004**: System MUST continuously monitor audio input for voice activity when recording is active
- **FR-005**: System MUST automatically detect speech pauses of 1-2 seconds duration and treat them as segment boundaries
- **FR-006**: System MUST send each detected audio segment to the ASR service at https://voicemodel.nickai.cc/v1/audio/transcriptions for transcription
- **FR-007**: System MUST format audio data as multipart/form-data with the audio file in the "file" field when sending to ASR API
- **FR-008**: System MUST parse the ASR API response format { "text": "辨識結果" } and extract the transcribed text
- **FR-009**: System MUST insert the first transcribed segment into the search box, replacing any placeholder text
- **FR-010**: System MUST append subsequent transcribed segments to existing text with appropriate spacing
- **FR-011**: System MUST display transcription results in real-time as each segment is processed, with a maximum delay of 2 seconds per segment
- **FR-012**: System MUST allow users to manually stop recording by clicking the microphone button again
- **FR-013**: System MUST allow users to cancel recording and discard any transcribed text
- **FR-014**: System MUST handle microphone permission denial gracefully with a clear user-friendly message
- **FR-015**: System MUST handle ASR API errors gracefully without disrupting the user experience
- **FR-016**: System MUST support browsers with Web Audio API and getUserMedia capabilities
- **FR-017**: System MUST stop recording automatically after [NEEDS CLARIFICATION: maximum recording duration - 60 seconds? 2 minutes? unlimited?] to prevent excessive resource usage

### Key Entities

- **VoiceInputSession**: Represents an active voice recording session, including recording state (idle/recording/processing), accumulated transcription segments, and timestamp of session start
- **AudioSegment**: Represents a discrete audio chunk detected between pauses, including raw audio data, duration, and timestamp
- **TranscriptionResult**: Represents the text output from the ASR service for a single audio segment, including transcribed text, confidence score (if provided), and processing timestamp

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can initiate voice input with a single click and see transcription results within 2 seconds of completing their speech
- **SC-002**: System accurately transcribes clear speech with >85% word accuracy for supported languages
- **SC-003**: System successfully handles continuous speech with multiple pauses, correctly concatenating segments into a coherent query
- **SC-004**: 90% of users successfully complete a voice search on their first attempt without needing to manually correct transcription errors
- **SC-005**: Voice input feature reduces average search query input time by 40% compared to typing for queries longer than 5 words
- **SC-006**: System gracefully handles microphone permission denials and API errors with user-friendly messages, maintaining a 100% error-free user experience (no crashes or blank screens)
