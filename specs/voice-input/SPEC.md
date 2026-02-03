# Voice Input Feature - 語音輸入功能

## Overview
為 AIKM 平台新增 VAD（Voice Activity Detection）語音輸入功能，讓使用者可以用語音進行搜尋。

## User Stories
1. 作為使用者，我想要點擊麥克風按鈕開始語音輸入
2. 作為使用者，我想要在說話時看到錄音狀態指示
3. 作為使用者，我想要說完一段話後自動辨識並填入搜尋框
4. 作為使用者，我想要連續說多段話，結果會累加

## Technical Requirements

### Frontend Components
- **VoiceInputButton**: 麥克風按鈕元件
  - 位置：搜尋框右側
  - 狀態：idle / recording / processing
  - 動畫：錄音中顯示紅點脈動，處理中顯示 spinner

### Dependencies
- `@ricky0123/vad-web`: VAD 語音活動偵測
- 需要 HTTPS（麥克風權限要求）

### ASR API Integration
- **Endpoint**: `https://voicemodel.nickai.cc/v1/audio/transcriptions`
- **Method**: POST
- **Content-Type**: multipart/form-data
- **Request Body**: 
  ```
  file: <audio blob>
  ```
- **Response**:
  ```json
  {
    "text": "辨識結果"
  }
  ```

### Flow
```
1. User clicks mic button
2. Request microphone permission
3. Start VAD listening
4. User speaks → VAD detects speech
5. User pauses → VAD triggers onSpeechEnd
6. Audio blob sent to ASR API
7. Response text appended to search input
8. Continue listening for more speech
9. User clicks mic button again to stop
```

### Error Handling
- 麥克風權限被拒絕：顯示提示訊息
- ASR API 失敗：顯示錯誤提示，不中斷錄音
- 網路斷線：graceful degradation

### UI States
| State | Button | Indicator |
|-------|--------|-----------|
| Idle | 🎤 灰色 | 無 |
| Recording | 🎤 紅色 | 紅點脈動 |
| Processing | 🎤 紅色 | Spinner |
| Error | 🎤 灰色 | 錯誤提示 |

## File Structure
```
frontend/
├── components/
│   └── VoiceInput/
│       ├── VoiceInputButton.tsx
│       ├── useVoiceInput.ts (custom hook)
│       └── index.ts
├── services/
│   └── asr.ts (ASR API client)
```

## Environment Variables
```env
NEXT_PUBLIC_ASR_API_URL=https://voicemodel.nickai.cc
```

## Acceptance Criteria
- [ ] 麥克風按鈕顯示在搜尋框右側
- [ ] 點擊後正確請求麥克風權限
- [ ] 錄音中顯示正確的視覺回饋
- [ ] 說話停頓後自動送出辨識
- [ ] 辨識結果正確填入搜尋框
- [ ] 連續說話結果會累加
- [ ] 再次點擊可停止錄音
- [ ] 錯誤情況有適當處理
