'use client';
import { useState } from 'react';
import { ThumbsUp, ThumbsDown } from '@carbon/icons-react';
import { apiPost } from '@/lib/api';

interface RagFeedbackButtonsProps {
  messageId: string;
  query: string;
  answer: string;
  onFeedbackSent?: (rating: 'up' | 'down') => void;
}

export default function RagFeedbackButtons({ messageId, query, answer, onFeedbackSent }: RagFeedbackButtonsProps) {
  const [sent, setSent] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [comment, setComment] = useState('');

  const send = async (rating: 'up' | 'down', commentText?: string) => {
    try {
      await apiPost('/api/chat/feedback', {
        message_id: messageId,
        query,
        rating,
        comment: commentText || undefined,
      });
      setSent(rating);
      setShowModal(false);
      onFeedbackSent?.(rating);
    } catch (e) {
      console.error('Feedback error:', e);
    }
  };

  if (sent) {
    return (
      <span style={{ fontSize: '0.75rem', color: '#42be65', marginLeft: '0.25rem' }}>
        {sent === 'up' ? '✓ 已標記為有用' : '✓ 已提交回饋'}
      </span>
    );
  }

  return (
    <>
      <div style={{ display: 'inline-flex', gap: '0.125rem' }}>
        <button
          onClick={() => send('up')}
          title="這個回答有幫助"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '0.125rem 0.375rem', borderRadius: 4,
            color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#42be65')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          <ThumbsUp size={14} />
        </button>
        <button
          onClick={() => setShowModal(true)}
          title="這個回答不好"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '0.125rem 0.375rem', borderRadius: 4,
            color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#da1e28')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          <ThumbsDown size={14} />
        </button>
      </div>

      {showModal && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}
          onClick={() => setShowModal(false)}
        >
          <div
            style={{
              background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)',
              padding: '1.5rem', width: '90%', maxWidth: 480,
              border: '1px solid var(--border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', color: 'var(--text-primary)' }}>回報問題</h3>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: '0 0 0.75rem' }}>
              可選：告訴我們這個回答哪裡有問題（內容錯誤、不相關、不完整等）
            </p>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="選填..."
              style={{
                width: '100%', minHeight: 80, padding: '0.625rem',
                fontSize: '0.875rem',
                background: 'var(--bg-primary)', color: 'var(--text-primary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                resize: 'vertical', boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
              <button
                onClick={() => setShowModal(false)}
                style={{
                  padding: '0.5rem 1rem', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)', background: 'transparent',
                  color: 'var(--text-muted)', cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={() => send('down', comment)}
                style={{
                  padding: '0.5rem 1rem', background: 'var(--accent)', color: 'white',
                  border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontWeight: 600,
                }}
              >
                提交
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
