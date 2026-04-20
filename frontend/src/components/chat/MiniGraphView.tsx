'use client';

import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { GraphNode, GraphLink } from '@/lib/mockGraphData';

interface MiniGraphViewProps {
  nodes: GraphNode[];
  links: GraphLink[];
  onNodeClick?: (node: GraphNode) => void;
  height?: number;
}

const nodeColors: Record<string, { bg: string; border: string }> = {
  Query: { bg: '#EFF6FF', border: '#3B82F6' },
  FaultCode: { bg: '#FEF2F2', border: '#EF4444' },
  SOP: { bg: '#F0FDF4', border: '#10B981' },
  WorkOrder: { bg: '#FFFBEB', border: '#F59E0B' },
  Asset: { bg: '#F5F3FF', border: '#8B5CF6' },
  Part: { bg: '#FDF4FF', border: '#D946EF' },
};

function CustomNode({ data }: NodeProps) {
  const type = data.type as string;
  const label = data.label as string;
  const colors = nodeColors[type] || nodeColors.Query;
  return (
    <div
      style={{
        padding: '8px 12px',
        borderRadius: 8,
        background: colors.bg,
        border: `2px solid ${colors.border}`,
        fontSize: 12,
        minWidth: 100,
        textAlign: 'center',
        whiteSpace: 'pre-line',
        color: '#111',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div style={{ fontSize: 10, color: '#666' }}>{type}</div>
      <div style={{ fontWeight: 600 }}>{label}</div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { custom: CustomNode };

export default function MiniGraphView({ nodes, links, onNodeClick, height = 260 }: MiniGraphViewProps) {
  const rfNodes: Node[] = useMemo(() => {
    // Layered layout：Query 置頂、FaultCode 中層、SOP/WorkOrder 底層展開
    const byType: Record<string, GraphNode[]> = {};
    nodes.forEach((n) => {
      byType[n.type] = byType[n.type] || [];
      byType[n.type].push(n);
    });
    const layerOrder = ['Query', 'FaultCode', 'SOP', 'WorkOrder', 'Asset', 'Part'];
    const positions: Record<string, { x: number; y: number }> = {};
    let y = 10;
    for (const layer of layerOrder) {
      const group = byType[layer] || [];
      if (group.length === 0) continue;
      const totalWidth = group.length * 160;
      const startX = 230 - totalWidth / 2 + 80;
      group.forEach((n, i) => {
        positions[n.id] = { x: startX + i * 160, y };
      });
      y += 110;
    }
    return nodes.map((n) => ({
      id: n.id,
      type: 'custom',
      position: positions[n.id] || { x: 50, y: 10 },
      data: { type: n.type, label: n.label, meta: n.meta, confidence: n.confidence },
    }));
  }, [nodes]);

  const rfEdges: Edge[] = useMemo(() => {
    return links.map((l, i) => ({
      id: `e${i}`,
      source: l.source,
      target: l.target,
      label: l.relation,
      labelStyle: { fontSize: 10, fill: '#666' },
      labelBgStyle: { fill: '#fff', fillOpacity: 0.8 },
      style: { stroke: '#9CA3AF', strokeWidth: 1.5 },
      animated: !!l.confidence && l.confidence > 0.85,
    }));
  }, [links]);

  const handleNodeClick = useCallback(
    (_: unknown, node: Node) => {
      if (!onNodeClick) return;
      const original = nodes.find((n) => n.id === node.id);
      if (original) onNodeClick(original);
    },
    [nodes, onNodeClick]
  );

  return (
    <div
      data-testid="mini-graph-view"
      style={{
        width: '100%',
        height,
        borderRadius: 8,
        border: '1px solid var(--border, #e5e7eb)',
        background: 'var(--bg-primary, #fff)',
      }}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        onNodeClick={handleNodeClick}
        panOnDrag
        zoomOnScroll
        minZoom={0.5}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
