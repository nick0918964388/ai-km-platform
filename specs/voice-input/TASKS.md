# Voice Input - 任務清單

## Phase 1: Setup
- [ ] 1.1 安裝 `@ricky0123/vad-web` 依賴
- [ ] 1.2 新增環境變數 `NEXT_PUBLIC_ASR_API_URL`

## Phase 2: ASR Service
- [ ] 2.1 建立 `frontend/services/asr.ts` - ASR API client
  - transcribe(audioBlob: Blob): Promise<string>

## Phase 3: Voice Input Hook
- [ ] 3.1 建立 `frontend/components/VoiceInput/useVoiceInput.ts`
  - 管理 VAD 實例
  - 處理麥克風權限
  - 管理錄音狀態 (idle/recording/processing)
  - 處理 onSpeechEnd 回調
  - 返回 { isRecording, isProcessing, error, startListening, stopListening }

## Phase 4: UI Component
- [ ] 4.1 建立 `frontend/components/VoiceInput/VoiceInputButton.tsx`
  - 麥克風圖示按鈕
  - 錄音狀態動畫（紅點脈動）
  - 處理中 spinner
  - 錯誤提示 tooltip

## Phase 5: Integration
- [ ] 5.1 在搜尋框元件中整合 VoiceInputButton
- [ ] 5.2 連接辨識結果到搜尋輸入框
- [ ] 5.3 處理連續輸入（累加文字）

## Phase 6: Testing & Polish
- [ ] 6.1 測試麥克風權限流程
- [ ] 6.2 測試 VAD 靈敏度
- [ ] 6.3 測試 ASR 辨識準確度
- [ ] 6.4 測試錯誤處理
- [ ] 6.5 調整 UI 動畫效果
