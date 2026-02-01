'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  Microphone,
  Image as ImageIcon,
  Close,
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import { Message, Attachment, SearchResult } from '@/types';
import SourcePreview from './SourcePreview';

interface ImagePreview {
  id: string;
  file: File;
  url: string;
  name: string;
}

interface MessageSources {
  [messageId: string]: SearchResult[];
}

export default function ChatWindow() {
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [imagePreviews, setImagePreviews] = useState<ImagePreview[]>([]);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [messageSources, setMessageSources] = useState<MessageSources>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);

  const {
    conversations,
    activeConversationId,
    addMessage,
    addConversation
  } = useStore();

  const activeConversation = conversations.find(c => c.id === activeConversationId);
  const messages = activeConversation?.messages || [];

  // Check if Web Speech API is supported
  useEffect(() => {
    setVoiceSupported('webkitSpeechRecognition' in window || 'SpeechRecognition' in window);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    let convId = activeConversationId;
    
    // Create new conversation if none active
    if (!convId) {
      const newConv = {
        id: Date.now().toString(),
        title: input.slice(0, 30) + (input.length > 30 ? '...' : ''),
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
      };
      addConversation(newConv);
      convId = newConv.id;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    addMessage(convId, userMessage);
    const userQuery = input;
    setInput('');
    setIsLoading(true);

    // Call backend API
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: userQuery,
          top_k: 5,
        }),
      });

      if (!response.ok) {
        throw new Error('API request failed');
      }

      const data = await response.json();
      const messageId = (Date.now() + 1).toString();

      const assistantMessage: Message = {
        id: messageId,
        role: 'assistant',
        content: data.answer || getSimulatedResponse(userQuery),
        timestamp: new Date(),
      };

      // Store sources for this message
      if (data.sources && data.sources.length > 0) {
        setMessageSources(prev => ({
          ...prev,
          [messageId]: data.sources,
        }));
      }

      addMessage(convId!, assistantMessage);
    } catch (error) {
      console.error('Chat API error:', error);
      // Fallback to simulated response
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: getSimulatedResponse(userQuery),
        timestamp: new Date(),
      };
      addMessage(convId!, assistantMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const getSimulatedResponse = (question: string): string => {
    const responses: Record<string, string> = {
      '引擎': '關於引擎問題，請提供更多細節：\n\n1. 車輛型號與年份\n2. 故障現象（異響、抖動、熄火等）\n3. 故障發生的時機\n\n我會根據這些資訊查詢相關維修知識。',
      '煞車': '煞車系統是車輛安全的關鍵。常見問題包括：\n\n- 煞車片磨損\n- 煞車油需要更換\n- 碟盤變形\n- ABS 系統故障\n\n請問您遇到的具體狀況是？',
      '保養': '定期保養對車輛壽命非常重要。建議的保養週期：\n\n- 機油更換：每 5,000-10,000 公里\n- 空氣濾清器：每 20,000 公里\n- 煞車油：每 2 年\n- 變速箱油：每 40,000 公里',
    };

    for (const [keyword, response] of Object.entries(responses)) {
      if (question.includes(keyword)) return response;
    }

    return `感謝您的提問！\n\n「${question}」\n\n我正在查詢相關的車輛維修知識庫。後端系統完成後，我將能夠提供更精確的維修建議和技術資料。\n\n目前您可以嘗試詢問關於：\n- 引擎問題\n- 煞車系統\n- 定期保養`;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Initialize Speech Recognition
  const initSpeechRecognition = useCallback(() => {
    if (!voiceSupported) return null;

    const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'zh-TW';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => setIsRecording(true);
    recognition.onend = () => setIsRecording(false);
    recognition.onerror = (event: any) => {
      console.error('Speech recognition error:', event.error);
      setIsRecording(false);
    };
    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        }
      }
      if (finalTranscript) {
        setInput(prev => prev + finalTranscript);
      }
    };

    return recognition;
  }, [voiceSupported]);

  const handleVoiceInput = () => {
    if (!voiceSupported) {
      alert('您的瀏覽器不支援語音輸入功能');
      return;
    }

    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    } else {
      const recognition = initSpeechRecognition();
      if (recognition) {
        recognitionRef.current = recognition;
        recognition.start();
      }
    }
  };

  // Cleanup speech recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const handleImageUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const newPreviews: ImagePreview[] = [];
      Array.from(files).forEach(file => {
        if (file.type.startsWith('image/')) {
          const url = URL.createObjectURL(file);
          newPreviews.push({
            id: `${Date.now()}-${file.name}`,
            file,
            url,
            name: file.name
          });
        }
      });
      setImagePreviews(prev => [...prev, ...newPreviews]);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeImagePreview = (id: string) => {
    setImagePreviews(prev => {
      const toRemove = prev.find(p => p.id === id);
      if (toRemove) {
        URL.revokeObjectURL(toRemove.url);
      }
      return prev.filter(p => p.id !== id);
    });
  };

  // Cleanup image URLs on unmount
  useEffect(() => {
    return () => {
      imagePreviews.forEach(preview => URL.revokeObjectURL(preview.url));
    };
  }, []);

  return (
    <div className="chat-container">
      <div className="chat-header">
        {activeConversation?.title || '開始新對話'}
      </div>

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div style={{
            textAlign: 'center',
            color: 'var(--text-secondary)',
            marginTop: '15vh',
            animation: 'fadeIn 0.5s ease'
          }}>
            <div style={{
              width: 80,
              height: 80,
              background: 'var(--bg-brand)',
              borderRadius: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.5rem',
              color: 'white',
              fontSize: '2rem',
              boxShadow: '0 8px 32px rgba(15, 98, 254, 0.2)'
            }}>
              🚗
            </div>
            <h2 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)', fontWeight: 600 }}>
              車輛維修知識庫
            </h2>
            <p style={{ marginBottom: '2rem', fontSize: '0.9375rem' }}>
              AI 智慧助理，隨時為您解答維修問題
            </p>
            <div style={{
              display: 'flex',
              gap: '0.75rem',
              justifyContent: 'center',
              flexWrap: 'wrap',
              maxWidth: 480,
              margin: '0 auto'
            }}>
              {['引擎異響怎麼辦？', '煞車有異音', '保養週期建議'].map((q) => (
                <button
                  key={q}
                  className="btn btn-secondary"
                  onClick={() => setInput(q)}
                  style={{
                    borderRadius: 20,
                    fontSize: '0.875rem',
                    padding: '0.625rem 1.25rem',
                    border: '1px solid var(--border)',
                    transition: 'all 0.2s'
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? 'U' : '🤖'}
              </div>
              <div className="message-content">
                {msg.content.split('\n').map((line, i) => (
                  <p key={i} style={{ margin: i === 0 ? 0 : '0.5rem 0 0' }}>
                    {line}
                  </p>
                ))}
                {/* Show sources with preview buttons for assistant messages */}
                {msg.role === 'assistant' && messageSources[msg.id] && messageSources[msg.id].length > 0 && (
                  <div className="message-sources">
                    <div className="sources-label">來源文件：</div>
                    <div className="sources-list">
                      {messageSources[msg.id].map((source, idx) => (
                        <div key={source.id} className="source-item">
                          <span className="source-name">[{idx + 1}] {source.document_name}</span>
                          <SourcePreview
                            fileUrl={source.file_url}
                            documentName={source.document_name}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="message assistant fade-in">
            <div className="message-avatar">🤖</div>
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        {/* Image Previews */}
        {imagePreviews.length > 0 && (
          <div className="image-preview-container">
            {imagePreviews.map(preview => (
              <div key={preview.id} className="image-preview-item">
                <img src={preview.url} alt={preview.name} />
                <button
                  className="image-preview-remove"
                  onClick={() => removeImagePreview(preview.id)}
                  title="移除圖片"
                >
                  <Close size={14} />
                </button>
                <span className="image-preview-name">{preview.name}</span>
              </div>
            ))}
          </div>
        )}

        <div className="chat-input-wrapper">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="image/*"
            multiple
            style={{ display: 'none' }}
          />

          <button
            className="input-btn"
            onClick={handleImageUpload}
            title="上傳圖片"
          >
            <ImageIcon size={20} />
          </button>

          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="輸入您的問題..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
          />

          {voiceSupported && (
            <button
              className={`input-btn ${isRecording ? 'recording' : ''}`}
              onClick={handleVoiceInput}
              title={isRecording ? '停止錄音' : '語音輸入'}
            >
              {isRecording ? (
                <div className="voice-level-indicator">
                  <div className="voice-level-bar"></div>
                  <div className="voice-level-bar"></div>
                  <div className="voice-level-bar"></div>
                  <div className="voice-level-bar"></div>
                  <div className="voice-level-bar"></div>
                </div>
              ) : (
                <Microphone size={20} />
              )}
            </button>
          )}

          <button
            className="input-btn primary"
            onClick={handleSend}
            disabled={(!input.trim() && imagePreviews.length === 0) || isLoading}
            title="發送"
          >
            <Send size={20} />
          </button>
        </div>
        {isRecording ? (
          <div style={{
            textAlign: 'center',
            fontSize: '0.8125rem',
            color: 'var(--primary)',
            marginTop: '0.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem'
          }}>
            <span className="recording-indicator" style={{
              padding: '0.25rem 0.75rem',
              background: 'var(--error-light)',
              color: 'var(--error)'
            }}>
              錄音中...
            </span>
            <span style={{ color: 'var(--text-secondary)' }}>點擊停止</span>
          </div>
        ) : (
          <div style={{
            textAlign: 'center',
            fontSize: '0.75rem',
            color: 'var(--text-placeholder)',
            marginTop: '0.5rem'
          }}>
            支援文字、語音、圖片輸入 | Enter 發送，Shift+Enter 換行
          </div>
        )}
      </div>

      <style jsx>{`
        .image-preview-container {
          display: flex;
          gap: 0.5rem;
          padding: 0.75rem;
          overflow-x: auto;
          background: var(--bg-secondary);
          border-radius: 8px 8px 0 0;
          border: 1px solid var(--border);
          border-bottom: none;
        }
        .image-preview-item {
          position: relative;
          flex-shrink: 0;
          width: 80px;
          height: 80px;
          border-radius: 8px;
          overflow: hidden;
          background: var(--bg-tertiary);
        }
        .image-preview-item img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .image-preview-remove {
          position: absolute;
          top: 4px;
          right: 4px;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: rgba(0, 0, 0, 0.6);
          border: none;
          color: white;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.15s;
        }
        .image-preview-remove:hover {
          background: rgba(218, 30, 40, 0.9);
        }
        .image-preview-name {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          padding: 2px 4px;
          background: rgba(0, 0, 0, 0.6);
          color: white;
          font-size: 0.625rem;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .input-btn.recording {
          background: var(--primary);
          color: white;
          animation: pulse-recording 1.5s infinite;
        }
        @keyframes pulse-recording {
          0%, 100% { box-shadow: 0 0 0 0 rgba(15, 98, 254, 0.4); }
          50% { box-shadow: 0 0 0 8px rgba(15, 98, 254, 0); }
        }
        .message-sources {
          margin-top: 1rem;
          padding-top: 0.75rem;
          border-top: 1px solid var(--border, #e0e0e0);
        }
        .sources-label {
          font-size: 0.75rem;
          color: var(--text-secondary, #6f6f6f);
          margin-bottom: 0.5rem;
        }
        .sources-list {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .source-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.75rem;
          padding: 0.5rem;
          background: var(--bg-secondary, #f4f4f4);
          border-radius: 6px;
          font-size: 0.8125rem;
        }
        .source-name {
          color: var(--text-primary, #161616);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          flex: 1;
          min-width: 0;
        }
      `}</style>
    </div>
  );
}
