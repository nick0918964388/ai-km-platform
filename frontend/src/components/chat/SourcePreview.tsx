'use client';

import { Document } from '@carbon/icons-react';
import { API_URL } from '@/lib/api';

interface SourcePreviewProps {
  documentId: string | null | undefined;
  documentName: string;
}

export default function SourcePreview({ documentId, documentName }: SourcePreviewProps) {
  const handlePreview = () => {
    if (!documentId) {
      alert('無法預覽：缺少文件識別碼');
      return;
    }

    const fullUrl = `${API_URL}/api/kb/documents/${documentId}/file`;
    window.open(fullUrl, '_blank');
  };

  if (!documentId) {
    return null;
  }

  return (
    <button
      className="source-preview-btn"
      onClick={handlePreview}
      title={`預覽 ${documentName}`}
    >
      <Document size={14} />
      <span>預覽原檔</span>

      <style jsx>{`
        .source-preview-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.25rem 0.5rem;
          font-size: 0.75rem;
          color: var(--primary, #0f62fe);
          background: var(--bg-brand-light, #e5f0ff);
          border: 1px solid var(--primary, #0f62fe);
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.15s ease;
          white-space: nowrap;
        }

        .source-preview-btn:hover {
          background: var(--primary, #0f62fe);
          color: white;
        }

        .source-preview-btn:active {
          transform: scale(0.98);
        }
      `}</style>
    </button>
  );
}
