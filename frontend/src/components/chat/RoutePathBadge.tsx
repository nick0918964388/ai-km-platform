'use client';

interface RoutePathBadgeProps {
  routePath: 'tool' | 'nl2sql';
  toolName?: string;
}

const TOOLTIPS = {
  tool: '此回答由 Maximo 工具直接查詢（tool-use），無需 SQL 轉換',
  nl2sql: '此回答由自然語言轉 SQL（NL2SQL）流程產生',
};

export default function RoutePathBadge({ routePath, toolName }: RoutePathBadgeProps) {
  const isTool = routePath === 'tool';
  const label = isTool ? (toolName ? `Tool: ${toolName}` : 'Tool') : 'NL2SQL';
  const icon = isTool ? '⚡' : '🧠';
  const tooltip = TOOLTIPS[routePath];

  return (
    <span
      title={tooltip}
      aria-label={`路由方式：${label} — ${tooltip}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        padding: '0.1rem 0.45rem',
        borderRadius: 99,
        fontSize: '0.6875rem',
        fontWeight: 600,
        lineHeight: 1.4,
        cursor: 'default',
        userSelect: 'none',
        background: isTool ? 'rgba(66, 190, 101, 0.12)' : 'rgba(80, 144, 211, 0.12)',
        color: isTool ? '#24a148' : '#0f62fe',
        border: `1px solid ${isTool ? 'rgba(66, 190, 101, 0.3)' : 'rgba(80, 144, 211, 0.3)'}`,
      }}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}
