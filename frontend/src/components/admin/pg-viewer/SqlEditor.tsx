'use client';

/**
 * SqlEditor — presentational Carbon-aligned textarea widget
 *
 * Aesthetic: terminal-style input frame, hard-left accent border, monospace
 * throughout.  No Monaco.  No rounded corners.  No decorative elements.
 */

import { useCallback, useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SqlEditorProps {
  value: string;
  onChange: (v: string) => void;
  /** Triggered on Ctrl/Cmd+Enter and by the parent Run button */
  onRun: () => void;
  disabled?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PLACEHOLDER = 'SELECT 1\n-- Ctrl/Cmd+Enter runs';

const MIN_ROWS = 10;
const MAX_ROWS = 20;
const LINE_HEIGHT_PX = 20; // matches font-size 13px / line-height 1.54

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SqlEditor({ value, onChange, onRun, disabled = false }: SqlEditorProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // ── Autoresize (min 10 rows, max 20 rows) ─────────────────────────────────
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Reset height so scrollHeight collapses to content
    el.style.height = 'auto';

    const minH = MIN_ROWS * LINE_HEIGHT_PX + 32; // 32px = top+bottom padding
    const maxH = MAX_ROWS * LINE_HEIGHT_PX + 32;
    const desired = Math.min(Math.max(el.scrollHeight, minH), maxH);
    el.style.height = `${desired}px`;
    el.style.overflowY = el.scrollHeight > maxH ? 'auto' : 'hidden';
  }, [value]);

  // ── Ctrl/Cmd+Enter keybind ────────────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!disabled) {
          onRun();
        }
      }
    },
    [disabled, onRun]
  );

  // ── Tab → insert 2 spaces (quality-of-life for SQL indentation) ───────────
  const handleTab = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const el = e.currentTarget;
        const start = el.selectionStart;
        const end = el.selectionEnd;
        const newValue = value.slice(0, start) + '  ' + value.slice(end);
        onChange(newValue);
        // Restore cursor position after the inserted spaces
        requestAnimationFrame(() => {
          el.selectionStart = start + 2;
          el.selectionEnd = start + 2;
        });
      }
    },
    [value, onChange]
  );

  return (
    <div
      style={{
        position: 'relative',
        borderLeft: '3px solid var(--accent, #0f62fe)',
        background: 'var(--bg-secondary, #161616)',
      }}
      data-testid="sql-editor-wrapper"
    >
      <textarea
        ref={ref}
        id="sql-editor-textarea"
        aria-label="SQL editor"
        aria-multiline="true"
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        data-gramm="false"
        value={value}
        placeholder={PLACEHOLDER}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          handleKeyDown(e);
          handleTab(e);
        }}
        style={{
          display: 'block',
          width: '100%',
          minHeight: `${MIN_ROWS * LINE_HEIGHT_PX + 32}px`,
          padding: '1rem 1.25rem',
          background: 'transparent',
          border: 'none',
          outline: 'none',
          resize: 'none',
          fontFamily: "'IBM Plex Mono', 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
          fontSize: '0.8125rem',
          lineHeight: `${LINE_HEIGHT_PX}px`,
          color: disabled ? 'var(--text-muted, #6f6f6f)' : 'var(--text-primary, #f4f4f4)',
          caretColor: 'var(--accent, #0f62fe)',
          cursor: disabled ? 'not-allowed' : 'text',
          boxSizing: 'border-box',
        }}
      />

      {/* Keyboard hint badge — right-aligned, fades when focused */}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          bottom: '0.5rem',
          right: '0.75rem',
          fontSize: '0.6875rem',
          fontFamily: 'monospace',
          color: 'var(--text-muted, #6f6f6f)',
          pointerEvents: 'none',
          userSelect: 'none',
          opacity: disabled ? 0 : 0.7,
          letterSpacing: '0.02em',
        }}
      >
        Ctrl/Cmd+Enter to run
      </span>
    </div>
  );
}
