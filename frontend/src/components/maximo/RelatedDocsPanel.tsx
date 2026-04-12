'use client';
import { useState, useEffect } from 'react';

interface RelatedDocsPanelProps {
  row?: Record<string, unknown> | null;
  autoSearch?: boolean;
  onClose?: () => void;
}

export default function RelatedDocsPanel({ row, autoSearch, onClose }: RelatedDocsPanelProps) {
  const [relatedDocs, setRelatedDocs] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const search = async (searchRow: Record<string, unknown>) => {
    setLoading(true);
    setRelatedDocs(null);
    const token = localStorage.getItem('auth_token');
    try {
      const body: any = { top_k: 5 };
      if (searchRow.wonum) body.wo_number = String(searchRow.wonum);
      if (searchRow.ticketid) body.wo_number = String(searchRow.ticketid);
      if (searchRow.description) body.description = String(searchRow.description);
      if (searchRow.assetnum) body.asset_num = String(searchRow.assetnum);

      const res = await fetch('/api/maximo/related-docs', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      setRelatedDocs(await res.json());
    } catch (e) {
      console.error('Related docs error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (autoSearch && row) {
      search(row);
    }
  }, [row, autoSearch]);

  const handleClose = () => {
    setRelatedDocs(null);
    onClose?.();
  };

  if (!loading && !relatedDocs) return null;

  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', padding: '1rem', marginTop: '0.75rem',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          📄 相關文件{relatedDocs ? `（${relatedDocs.total_found} 筆）` : ''}
        </div>
        <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.875rem' }}>✕</button>
      </div>

      {loading && <div style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>搜尋中...</div>}

      {relatedDocs && relatedDocs.documents && relatedDocs.documents.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {relatedDocs.documents.map((doc: any, i: number) => (
            <div key={i} style={{
              padding: '0.75rem', background: 'var(--bg-primary)',
              borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--text-primary)' }}>
                  {doc.document_name}
                </div>
                <div style={{
                  fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: 4,
                  background: doc.score >= 0.7 ? 'rgba(66,190,101,0.15)' : 'rgba(241,194,50,0.15)',
                  color: doc.score >= 0.7 ? '#42be65' : '#f1c232',
                }}>
                  {doc.source === 'mapping' ? '精確對應' : `相關度 ${Math.round(doc.score * 100)}%`}
                </div>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                {doc.match_type}
              </div>
              {doc.content_preview && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem', lineHeight: 1.5 }}>
                  {doc.content_preview}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : relatedDocs && !loading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
          未找到相關文件。上傳更多 SOP 文件可以提升關聯效果。
        </div>
      ) : null}

      {relatedDocs?.query_context && (
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          搜尋條件：{relatedDocs.query_context.substring(0, 100)}
        </div>
      )}
    </div>
  );
}
