'use client';

import { useState, useEffect, useRef } from 'react';
import { getApiHeaders, API_URL } from '@/lib/api';

interface ModelInfo {
  name: string;
  size?: string;
}

interface ModelSelectorProps {
  selectedModel: string;
  onModelChange: (model: string) => void;
}

export default function ModelSelector({ selectedModel, onModelChange }: ModelSelectorProps) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/models`, { headers: getApiHeaders() })
      .then(r => r.json())
      .then(data => {
        if (data.models?.length) setModels(data.models);
        if (data.current && !selectedModel) onModelChange(data.current);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const displayName = selectedModel || 'Default';

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        title="切換模型"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.375rem',
          padding: '0.25rem 0.5rem',
          background: 'transparent',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text-secondary)',
          fontSize: '0.75rem',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
          maxWidth: 140,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        <span style={{ fontSize: '0.75rem' }}>⚙</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayName}</span>
        <span style={{ fontSize: '0.625rem', flexShrink: 0 }}>▾</span>
      </button>
      {open && models.length > 0 && (
        <div style={{
          position: 'absolute',
          bottom: 'calc(100% + 6px)',
          left: 0,
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          minWidth: 180,
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
          zIndex: 200,
          overflow: 'hidden',
        }}>
          {models.map(m => (
            <button
              key={m.name}
              onClick={() => { onModelChange(m.name); setOpen(false); }}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '0.5rem',
                padding: '0.5rem 0.75rem',
                background: m.name === selectedModel ? 'var(--primary-light)' : 'transparent',
                border: 'none',
                color: m.name === selectedModel ? 'var(--accent)' : 'var(--text-primary)',
                fontSize: '0.8125rem',
                cursor: 'pointer',
                textAlign: 'left',
              }}
              onMouseEnter={(e) => { if (m.name !== selectedModel) e.currentTarget.style.background = 'var(--bg-tertiary)'; }}
              onMouseLeave={(e) => { if (m.name !== selectedModel) e.currentTarget.style.background = 'transparent'; }}
            >
              <span>{m.name}</span>
              {m.name === selectedModel && <span style={{ fontSize: '0.75rem' }}>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
