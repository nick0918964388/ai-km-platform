'use client';

import { useId } from 'react';
import { Button } from '@carbon/react';
import { Add, TrashCan } from '@carbon/icons-react';
import type { FilterClauseExt } from '@/hooks/useTableRows';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OPS: FilterClauseExt['op'][] = [
  '=',
  '!=',
  '<',
  '<=',
  '>',
  '>=',
  'LIKE',
  'ILIKE',
  'IN',
  'NOT IN',
  'IS NULL',
  'IS NOT NULL',
];

/** Operators that don't require a value field */
const NO_VALUE_OPS = new Set<FilterClauseExt['op']>(['IS NULL', 'IS NOT NULL']);

/** Operators that accept comma-separated lists */
const LIST_OPS = new Set<FilterClauseExt['op']>(['IN', 'NOT IN']);

/** Operators that support wildcard toggle */
const LIKE_OPS = new Set<FilterClauseExt['op']>(['LIKE', 'ILIKE']);

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface FilterBarProps {
  columns: string[];
  filters: FilterClauseExt[];
  onChange: (filters: FilterClauseExt[]) => void;
}

// ---------------------------------------------------------------------------
// Sub-component: single filter row
// ---------------------------------------------------------------------------

interface FilterRowProps {
  filter: FilterClauseExt;
  columns: string[];
  rowIndex: number;
  onUpdate: (updated: FilterClauseExt) => void;
  onRemove: () => void;
  baseId: string;
}

function FilterRow({ filter, columns, rowIndex, onUpdate, onRemove, baseId }: FilterRowProps) {
  const colId = `${baseId}-col-${rowIndex}`;
  const opId = `${baseId}-op-${rowIndex}`;
  const valId = `${baseId}-val-${rowIndex}`;
  const wildcardId = `${baseId}-wc-${rowIndex}`;

  const noValue = NO_VALUE_OPS.has(filter.op);
  const isList = LIST_OPS.has(filter.op);
  const isLike = LIKE_OPS.has(filter.op);

  // Wildcard toggle: true if value contains % on either end
  const hasWildcard =
    typeof filter.value === 'string' &&
    (filter.value.startsWith('%') || filter.value.endsWith('%'));

  const handleColChange = (col: string) => {
    onUpdate({ ...filter, column: col });
  };

  const handleOpChange = (op: FilterClauseExt['op']) => {
    // Clear value when switching to/from no-value ops
    const newValue = NO_VALUE_OPS.has(op) ? undefined : filter.value;
    onUpdate({ ...filter, op, value: newValue });
  };

  const handleValueChange = (raw: string) => {
    onUpdate({ ...filter, value: raw === '' ? undefined : raw });
  };

  const handleWildcardToggle = () => {
    const current = typeof filter.value === 'string' ? filter.value : '';
    // Strip existing wildcards, then re-add if toggling on
    const stripped = current.replace(/^%/, '').replace(/%$/, '');
    const next = hasWildcard ? stripped : `%${stripped}%`;
    onUpdate({ ...filter, value: next === '' ? undefined : next });
  };

  const cellStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.125rem',
    minWidth: 0,
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '0.6875rem',
    color: 'var(--text-muted)',
    fontWeight: 500,
    letterSpacing: '0.02em',
    userSelect: 'none',
  };

  const selectStyle: React.CSSProperties = {
    width: '100%',
    height: 32,
    padding: '0 0.5rem',
    background: 'var(--bg-tertiary)',
    border: '1px solid var(--border-light)',
    borderRadius: 'var(--radius-sm, 4px)',
    color: 'var(--text-primary)',
    fontSize: '0.8125rem',
    fontFamily: 'monospace',
    cursor: 'pointer',
    outline: 'none',
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    height: 32,
    padding: '0 0.5rem',
    background: 'var(--bg-tertiary)',
    border: '1px solid var(--border-light)',
    borderRadius: 'var(--radius-sm, 4px)',
    color: 'var(--text-primary)',
    fontSize: '0.8125rem',
    fontFamily: 'monospace',
    outline: 'none',
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 120px 1fr auto',
        gap: '0.5rem',
        alignItems: 'end',
        padding: '0.5rem',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-light)',
        borderRadius: 'var(--radius-sm, 4px)',
      }}
    >
      {/* Column selector */}
      <div style={cellStyle}>
        <label htmlFor={colId} style={labelStyle}>欄位</label>
        <select
          id={colId}
          value={filter.column}
          onChange={(e) => handleColChange(e.target.value)}
          style={selectStyle}
        >
          {columns.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* Operator selector */}
      <div style={cellStyle}>
        <label htmlFor={opId} style={labelStyle}>運算子</label>
        <select
          id={opId}
          value={filter.op}
          onChange={(e) => handleOpChange(e.target.value as FilterClauseExt['op'])}
          style={selectStyle}
        >
          {OPS.map((op) => (
            <option key={op} value={op}>{op}</option>
          ))}
        </select>
      </div>

      {/* Value input (hidden for IS NULL / IS NOT NULL) */}
      <div style={cellStyle}>
        {!noValue && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', height: '1rem' }}>
              <label htmlFor={valId} style={labelStyle}>
                {isList ? '值（逗號分隔）' : '值'}
              </label>
              {isLike && (
                <label
                  htmlFor={wildcardId}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    fontSize: '0.6875rem',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    userSelect: 'none',
                    marginLeft: 'auto',
                  }}
                >
                  <input
                    id={wildcardId}
                    type="checkbox"
                    checked={hasWildcard}
                    onChange={handleWildcardToggle}
                    style={{ accentColor: 'var(--accent)', width: 12, height: 12 }}
                  />
                  % 通配符
                </label>
              )}
            </div>
            <input
              id={valId}
              type="text"
              value={typeof filter.value === 'string' ? filter.value : filter.value != null ? String(filter.value) : ''}
              onChange={(e) => handleValueChange(e.target.value)}
              placeholder={isList ? 'val1,val2,val3' : isLike ? '%keyword%' : ''}
              style={inputStyle}
            />
          </>
        )}
        {noValue && (
          <div style={{ height: 32, display: 'flex', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              無需值
            </span>
          </div>
        )}
      </div>

      {/* Remove button */}
      <div style={{ alignSelf: 'flex-end' }}>
        <button
          type="button"
          onClick={onRemove}
          title="移除此篩選條件"
          aria-label="移除此篩選條件"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 32,
            height: 32,
            background: 'transparent',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm, 4px)',
            color: 'var(--text-muted)',
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--error)';
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--error)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-light)';
          }}
        >
          <TrashCan size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main FilterBar component
// ---------------------------------------------------------------------------

export function FilterBar({ columns, filters, onChange }: FilterBarProps) {
  const baseId = useId();

  const addFilter = () => {
    const newFilter: FilterClauseExt = {
      column: columns[0] ?? '',
      op: '=',
      value: undefined,
    };
    onChange([...filters, newFilter]);
  };

  const updateFilter = (index: number, updated: FilterClauseExt) => {
    const next = [...filters];
    next[index] = updated;
    onChange(next);
  };

  const removeFilter = (index: number) => {
    onChange(filters.filter((_, i) => i !== index));
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.375rem',
      }}
      aria-label="篩選條件列表"
    >
      {filters.map((f, i) => (
        <FilterRow
          key={i}
          filter={f}
          columns={columns}
          rowIndex={i}
          baseId={baseId}
          onUpdate={(updated) => updateFilter(i, updated)}
          onRemove={() => removeFilter(i)}
        />
      ))}

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: filters.length > 0 ? '0.25rem' : 0 }}>
        <Button
          kind="ghost"
          size="sm"
          renderIcon={Add}
          onClick={addFilter}
          disabled={columns.length === 0}
        >
          新增篩選條件
        </Button>

        {filters.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              fontSize: '0.75rem',
              cursor: 'pointer',
              textDecoration: 'underline',
            }}
          >
            清除全部
          </button>
        )}
      </div>
    </div>
  );
}
