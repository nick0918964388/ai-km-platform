'use client';

import { useState } from 'react';

export interface Step {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
}

interface TaskProgressProps {
  steps: Step[];
  isExpanded?: boolean;
}

function Spinner() {
  return (
    <span style={{
      display: 'inline-block',
      width: 14,
      height: 14,
      border: '2px solid var(--border)',
      borderTopColor: 'var(--accent)',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
      flexShrink: 0,
    }} />
  );
}

const statusIcon = (status: Step['status']) => {
  if (status === 'running') return <Spinner />;
  if (status === 'done') return (
    <span style={{ color: '#24a148', fontSize: '0.875rem', flexShrink: 0 }}>✓</span>
  );
  if (status === 'error') return (
    <span style={{ color: '#da1e28', fontSize: '0.875rem', flexShrink: 0 }}>✗</span>
  );
  return (
    <span style={{
      display: 'inline-block',
      width: 14,
      height: 14,
      border: '2px solid var(--border)',
      borderRadius: '50%',
      flexShrink: 0,
    }} />
  );
};

export default function TaskProgress({ steps, isExpanded: defaultExpanded = false }: TaskProgressProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (!steps || steps.length === 0) return null;

  const runningCount = steps.filter(s => s.status === 'running').length;
  const doneCount = steps.filter(s => s.status === 'done').length;
  const hasRunning = runningCount > 0;
  const allDone = doneCount === steps.length;

  const summaryText = allDone
    ? `已完成 ${steps.length} 個步驟`
    : hasRunning
    ? `正在處理... ${doneCount}/${steps.length} 步驟`
    : `準備中... ${steps.length} 個步驟`;

  return (
    <div style={{
      marginBottom: '0.75rem',
      background: 'var(--bg-tertiary)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
      fontSize: '0.8125rem',
    }}>
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.5rem 0.75rem',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--text-secondary)',
          textAlign: 'left',
        }}
      >
        {hasRunning && !allDone ? <Spinner /> : (
          <span style={{ color: allDone ? '#24a148' : 'var(--text-muted)', fontSize: '0.75rem' }}>
            {allDone ? '✓' : '◦'}
          </span>
        )}
        <span style={{ flex: 1 }}>{summaryText}</span>
        <span style={{
          fontSize: '0.6875rem',
          color: 'var(--text-muted)',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s',
        }}>▼</span>
      </button>
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '0.5rem 0' }}>
          {steps.map((step) => (
            <div key={step.id} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.625rem',
              padding: '0.375rem 0.75rem',
              color: step.status === 'pending' ? 'var(--text-muted)' : 'var(--text-primary)',
            }}>
              {statusIcon(step.status)}
              <span style={{ fontSize: '0.8125rem' }}>{step.label}</span>
            </div>
          ))}
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
