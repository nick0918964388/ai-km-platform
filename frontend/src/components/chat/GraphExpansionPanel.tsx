'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import type { GraphExpansionData, WorkOrderItem, SopItem, PartItem } from '@/lib/mockGraphData';
import { MOCK_MINI_GRAPH } from '@/lib/mockGraphData';

const MiniGraphView = dynamic(() => import('./MiniGraphView'), { ssr: false });

interface GraphExpansionPanelProps {
  messageId: string;
  data?: GraphExpansionData;
  onItemClick?: (type: 'workorder' | 'sop' | 'part', id: string) => void;
}

type SectionKey = 'workorders' | 'sops' | 'parts' | 'graph';

function SectionHeader({
  icon,
  title,
  count,
  expanded,
  onToggle,
}: {
  icon: string;
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      aria-expanded={expanded}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        width: '100%',
        padding: '0.5rem 0.75rem',
        background: 'var(--bg-primary)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        cursor: 'pointer',
        fontSize: '0.8125rem',
        color: 'var(--text-primary)',
        textAlign: 'left',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-secondary)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--bg-primary)')}
    >
      <span
        style={{
          color: 'var(--text-muted)',
          fontSize: '0.75rem',
          transition: 'transform 0.2s ease',
          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
        }}
      >
        ▶
      </span>
      <span style={{ fontSize: '0.95rem' }}>{icon}</span>
      <span style={{ flex: 1, fontWeight: 500 }}>{title}</span>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          minWidth: '1.25rem',
          height: '1.25rem',
          padding: '0 0.375rem',
          background: 'var(--primary-light, rgba(37, 99, 235, 0.12))',
          color: 'var(--accent)',
          borderRadius: 10,
          fontSize: '0.6875rem',
          fontWeight: 600,
        }}
      >
        {count}
      </span>
    </button>
  );
}

function ItemRow({
  primary,
  secondary,
  score,
  tooltip,
  onClick,
}: {
  primary: React.ReactNode;
  secondary?: React.ReactNode;
  score?: { label: string; value: number };
  tooltip: string;
  onClick?: () => void;
}) {
  const scoreColor = (v: number) => (v > 0.8 ? '#24a148' : v >= 0.5 ? '#f1c21b' : '#da1e28');

  return (
    <div
      title={tooltip}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.5rem 0.75rem',
        background: 'var(--bg-secondary)',
        borderRadius: 'var(--radius-sm)',
        cursor: onClick ? 'pointer' : 'default',
        fontSize: '0.8125rem',
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-tertiary, #eee)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--bg-secondary)')}
    >
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
        <div
          style={{
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            color: 'var(--text-primary)',
          }}
        >
          {primary}
        </div>
        {secondary && (
          <div
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
              marginTop: 2,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {secondary}
          </div>
        )}
      </div>
      {score && (
        <span
          style={{
            flexShrink: 0,
            fontSize: '0.6875rem',
            fontWeight: 600,
            color: scoreColor(score.value),
            padding: '0.125rem 0.375rem',
            background: `${scoreColor(score.value)}15`,
            borderRadius: 4,
          }}
        >
          {score.label} {Math.round(score.value * 100)}%
        </span>
      )}
    </div>
  );
}

export default function GraphExpansionPanel({ messageId, data, onItemClick }: GraphExpansionPanelProps) {
  const [expanded, setExpanded] = useState<Record<SectionKey, boolean>>({
    workorders: false,
    sops: false,
    parts: false,
    graph: false,
  });

  if (!data) return null;

  const wos = (data.similarWorkOrders || []).slice(0, 3);
  const sops = (data.recommendedSops || []).slice(0, 3);
  const parts = (data.commonParts || []).slice(0, 3);

  const hasAny = wos.length > 0 || sops.length > 0 || parts.length > 0;
  if (!hasAny) return null;

  const toggle = (k: SectionKey) => setExpanded((p) => ({ ...p, [k]: !p[k] }));

  return (
    <div
      data-testid="graph-expansion-panel"
      data-message-id={messageId}
      style={{
        marginTop: '1rem',
        paddingTop: '0.75rem',
        borderTop: '1px solid var(--border)',
      }}
    >
      <div
        style={{
          color: 'var(--text-muted)',
          marginBottom: '0.5rem',
          fontSize: '0.75rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem',
        }}
      >
        🕸️ 知識圖譜擴展
      </div>

      <div
        style={{
          display: 'grid',
          gap: '0.5rem',
          gridTemplateColumns: '1fr',
        }}
        className="graph-expansion-grid"
      >
        {/* Similar Work Orders */}
        {wos.length > 0 && (
          <section data-testid="section-workorders">
            <SectionHeader
              icon="🔗"
              title="相關工單"
              count={wos.length}
              expanded={expanded.workorders}
              onToggle={() => toggle('workorders')}
            />
            {expanded.workorders && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem', marginTop: '0.375rem' }}>
                {wos.map((w: WorkOrderItem) => (
                  <ItemRow
                    key={w.wonum}
                    primary={
                      <>
                        <span style={{ fontFamily: 'monospace', color: 'var(--accent)', marginRight: '0.5rem' }}>
                          {w.wonum}
                        </span>
                        {w.description}
                      </>
                    }
                    secondary={`${w.status} · ${w.reportdate}`}
                    score={w.similarityScore != null ? { label: '相似', value: w.similarityScore } : undefined}
                    tooltip={`工單 ${w.wonum}｜狀態 ${w.status}｜回報 ${w.reportdate}${
                      w.similarityScore != null ? `｜相似度 ${(w.similarityScore * 100).toFixed(0)}%` : ''
                    }${w.confidence != null ? `｜信心 ${(w.confidence * 100).toFixed(0)}%` : ''}`}
                    onClick={onItemClick ? () => onItemClick('workorder', w.wonum) : undefined}
                  />
                ))}
                <button
                  style={{
                    alignSelf: 'flex-end',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--accent)',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    padding: '0.25rem 0.5rem',
                  }}
                >
                  查看更多 →
                </button>
              </div>
            )}
          </section>
        )}

        {/* Recommended SOPs */}
        {sops.length > 0 && (
          <section data-testid="section-sops">
            <SectionHeader
              icon="📋"
              title="建議 SOP"
              count={sops.length}
              expanded={expanded.sops}
              onToggle={() => toggle('sops')}
            />
            {expanded.sops && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem', marginTop: '0.375rem' }}>
                {sops.map((s: SopItem) => (
                  <ItemRow
                    key={s.sopId}
                    primary={
                      <>
                        <span style={{ fontFamily: 'monospace', color: 'var(--accent)', marginRight: '0.5rem' }}>
                          {s.sopId}
                        </span>
                        {s.title}
                      </>
                    }
                    secondary={`版本 ${s.version}`}
                    score={s.successRate != null ? { label: '成功率', value: s.successRate } : undefined}
                    tooltip={`${s.sopId}｜${s.title}｜版本 ${s.version}${
                      s.successRate != null ? `｜成功率 ${(s.successRate * 100).toFixed(0)}%` : ''
                    }`}
                    onClick={onItemClick ? () => onItemClick('sop', s.sopId) : undefined}
                  />
                ))}
                <button
                  style={{
                    alignSelf: 'flex-end',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--accent)',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    padding: '0.25rem 0.5rem',
                  }}
                >
                  查看更多 →
                </button>
              </div>
            )}
          </section>
        )}

        {/* Common Parts */}
        {parts.length > 0 && (
          <section data-testid="section-parts">
            <SectionHeader
              icon="🔧"
              title="常用零件"
              count={parts.length}
              expanded={expanded.parts}
              onToggle={() => toggle('parts')}
            />
            {expanded.parts && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem', marginTop: '0.375rem' }}>
                {parts.map((p: PartItem) => (
                  <ItemRow
                    key={p.partId}
                    primary={
                      <>
                        <span style={{ fontFamily: 'monospace', color: 'var(--accent)', marginRight: '0.5rem' }}>
                          {p.partId}
                        </span>
                        {p.name}
                      </>
                    }
                    secondary={[p.manufacturer, p.frequency != null ? `使用 ${p.frequency} 次` : null]
                      .filter(Boolean)
                      .join(' · ')}
                    tooltip={`${p.partId}｜${p.name}${p.manufacturer ? `｜製造商 ${p.manufacturer}` : ''}${
                      p.frequency != null ? `｜出現頻次 ${p.frequency}` : ''
                    }`}
                    onClick={onItemClick ? () => onItemClick('part', p.partId) : undefined}
                  />
                ))}
                <button
                  style={{
                    alignSelf: 'flex-end',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--accent)',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    padding: '0.25rem 0.5rem',
                  }}
                >
                  查看更多 →
                </button>
              </div>
            )}
          </section>
        )}
      </div>

      {/* Mini Graph 路徑視圖 */}
      <section data-testid="section-graph" style={{ marginTop: '0.5rem' }}>
        <SectionHeader
          icon="🕸️"
          title="圖路徑"
          count={MOCK_MINI_GRAPH.nodes.length}
          expanded={expanded.graph}
          onToggle={() => toggle('graph')}
        />
        {expanded.graph && (
          <div style={{ marginTop: '0.375rem' }}>
            <MiniGraphView
              nodes={MOCK_MINI_GRAPH.nodes}
              links={MOCK_MINI_GRAPH.links}
              onNodeClick={(n) => console.log('mini-graph node clicked:', n)}
            />
          </div>
        )}
      </section>

      <style jsx>{`
        @media (min-width: 1024px) {
          :global(.graph-expansion-grid) {
            grid-template-columns: repeat(3, 1fr) !important;
            align-items: start;
          }
        }
      `}</style>
    </div>
  );
}
