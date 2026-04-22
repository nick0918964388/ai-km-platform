'use client';
import { useState } from 'react';
import { ThumbsUp, ThumbsDown } from '@carbon/icons-react';
import { apiPost } from '@/lib/api';

interface FeedbackButtonsProps {
  question: string;
  sql: string;
  onFeedbackSent?: (rating: 'up' | 'down') => void;
}

export default function FeedbackButtons({ question, sql, onFeedbackSent }: FeedbackButtonsProps) {
  const [feedbackSent, setFeedbackSent] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [correctedSQL, setCorrectedSQL] = useState('');

  const handleFeedback = async (rating: 'up' | 'down', corrected?: string) => {
    try {
      await apiPost('/api/maximo/feedback', {
        question,
        sql,
        rating,
        corrected_sql: corrected || undefined,
      });
      setFeedbackSent(rating);
      setShowModal(false);
      onFeedbackSent?.(rating);
    } catch (e) {
      console.error('Feedback error:', e);
    }
  };

  if (feedbackSent) {
    return (
      <span style={{ fontSize: '0.75rem', color: '#42be65', marginLeft: '0.5rem' }}>
        {feedbackSent === 'up' ? '✓ 已標記為正確' : '✓ 已提交回饋'}
      </span>
    );
  }

  return (
    <>
      <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.5rem' }}>
        <button onClick={() => handleFeedback('up')} title="查詢正確" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.125rem 0.375rem', borderRadius: 4, color: 'var(--text-muted)' }}>
          <ThumbsUp size={14} />
        </button>
        <button onClick={() => { setShowModal(true); setCorrectedSQL(sql); }} title="查詢有誤" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.125rem 0.375rem', borderRadius: 4, color: 'var(--text-muted)' }}>
          <ThumbsDown size={14} />
        </button>
      </div>

      {showModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setShowModal(false)}>
          <div style={{
            background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)',
            padding: '1.5rem', width: '90%', maxWidth: 600,
            border: '1px solid var(--border)',
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: 'var(--text-primary)' }}>修正 SQL</h3>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: '0 0 0.75rem' }}>
              請修正下方 SQL，修正後會加入範例庫提升未來查詢品質：
            </p>
            <textarea
              value={correctedSQL}
              onChange={e => setCorrectedSQL(e.target.value)}
              style={{
                width: '100%', minHeight: 120, padding: '0.75rem',
                fontFamily: 'monospace', fontSize: '0.8125rem',
                background: 'var(--bg-primary)', color: 'var(--text-primary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                resize: 'vertical',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
              <button onClick={() => { handleFeedback('down'); }} style={{
                padding: '0.5rem 1rem', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', background: 'transparent',
                color: 'var(--text-muted)', cursor: 'pointer',
              }}>
                不修正，僅回報問題
              </button>
              <button onClick={() => { handleFeedback('down', correctedSQL); }} style={{
                padding: '0.5rem 1rem', background: 'var(--primary)', color: 'white',
                border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontWeight: 600,
              }}>
                提交修正
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
