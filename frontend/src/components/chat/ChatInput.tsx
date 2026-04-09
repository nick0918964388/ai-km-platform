'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, StopFilled, Attachment } from '@carbon/icons-react';
import ModelSelector from './ModelSelector';
import { VoiceInputButton } from '@/components/VoiceInput';

interface ChatInputProps {
  onSend: (query: string, imageBase64?: string, model?: string) => void;
  onStop: () => void;
  isLoading: boolean;
  selectedModel: string;
  onModelChange: (model: string) => void;
}

export default function ChatInput({
  onSend,
  onStop,
  isLoading,
  selectedModel,
  onModelChange,
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [imageBase64, setImageBase64] = useState<string | undefined>(undefined);
  const [imagePreview, setImagePreview] = useState<string | undefined>(undefined);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const handleFileChange = (file: File) => {
    if (!file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      setImagePreview(result);
      setImageBase64(result.split(',')[1]);
    };
    reader.readAsDataURL(file);
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) handleFileChange(file);
        break;
      }
    }
  };

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    const query = input.trim();
    setInput('');
    setImageBase64(undefined);
    setImagePreview(undefined);
    onSend(query, imageBase64, selectedModel);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const removeImage = () => {
    setImageBase64(undefined);
    setImagePreview(undefined);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div style={{
      padding: '0.5rem 2rem 1rem',
      background: 'transparent',
      flexShrink: 0,
    }}>
      <div style={{
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        background: 'rgba(var(--bg-primary-rgb, 255,255,255), 0.85)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
        overflow: 'hidden',
      }}>
        {/* Image preview strip */}
        {imagePreview && (
          <div style={{
            padding: '0.5rem 1rem',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}>
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <img
                src={imagePreview}
                alt="附件預覽"
                style={{
                  height: 56,
                  maxWidth: 120,
                  objectFit: 'cover',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border)',
                }}
              />
              <button
                onClick={removeImage}
                style={{
                  position: 'absolute',
                  top: -6,
                  right: -6,
                  width: 18,
                  height: 18,
                  borderRadius: '50%',
                  background: 'var(--text-muted)',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.625rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Input row */}
        <div style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: '0.5rem',
          padding: '0.625rem 0.75rem',
        }}>
          {/* Left: attach + model */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', flexShrink: 0, paddingBottom: 4 }}>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileChange(file);
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              title="上傳附件"
              style={{
                width: 32,
                height: 32,
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--radius-sm)',
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = 'var(--accent)'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
            >
              <Attachment size={18} />
            </button>
            <ModelSelector selectedModel={selectedModel} onModelChange={onModelChange} />
          </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            placeholder="輸入您的問題... (Shift+Enter 換行)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            rows={1}
            style={{
              flex: 1,
              border: 'none',
              background: 'transparent',
              padding: '0.375rem 0',
              fontSize: '0.9375rem',
              color: 'var(--text-primary)',
              resize: 'none',
              minHeight: 28,
              maxHeight: 150,
              outline: 'none',
              lineHeight: 1.5,
            }}
          />

          {/* Right: voice + send/stop */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', flexShrink: 0, paddingBottom: 4 }}>
            <VoiceInputButton
              onTranscriptionReceived={(text) => {
                setInput((prev) => prev ? `${prev} ${text}` : text);
              }}
            />
            {isLoading ? (
              <button
                onClick={onStop}
                title="停止"
                style={{
                  width: 36,
                  height: 36,
                  border: 'none',
                  background: 'var(--text-muted)',
                  borderRadius: 10,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                }}
              >
                <StopFilled size={18} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                title="發送"
                style={{
                  width: 36,
                  height: 36,
                  border: 'none',
                  background: 'var(--primary)',
                  borderRadius: 10,
                  cursor: input.trim() ? 'pointer' : 'not-allowed',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                  opacity: input.trim() ? 1 : 0.45,
                }}
              >
                <Send size={18} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
