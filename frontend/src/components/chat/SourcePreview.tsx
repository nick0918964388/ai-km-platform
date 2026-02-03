'use client';

import { useState, useEffect, useCallback } from 'react';
import { Document, Close } from '@carbon/icons-react';
import { API_URL } from '@/lib/api';
import { createPortal } from 'react-dom';

interface SourcePreviewProps {
  documentId: string | null | undefined;
  documentName: string;
}

type PreviewType = 'pdf' | 'word' | 'excel' | 'image' | 'unknown';

function getPreviewType(filename: string): PreviewType {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (ext === 'pdf') return 'pdf';
  if (['doc', 'docx'].includes(ext)) return 'word';
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'excel';
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image';
  return 'unknown';
}

function PreviewModal({
  documentId,
  documentName,
  onClose,
}: {
  documentId: string;
  documentName: string;
  onClose: () => void;
}) {
  const fileUrl = `${API_URL}/api/kb/documents/${documentId}/file`;
  const previewType = getPreviewType(documentName);

  // Close on ESC
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  const renderContent = () => {
    switch (previewType) {
      case 'pdf':
        return (
          <iframe
            src={fileUrl}
            style={{
              width: '100%',
              height: '100%',
              border: 'none',
              borderRadius: '0 0 12px 12px',
            }}
            title={documentName}
          />
        );
      case 'word':
      case 'excel': {
        // Build absolute URL for Google Docs Viewer
        const absoluteUrl = fileUrl.startsWith('http')
          ? fileUrl
          : `${window.location.origin}${fileUrl}`;
        const viewerUrl = `https://docs.google.com/viewer?url=${encodeURIComponent(absoluteUrl)}&embedded=true`;
        return (
          <iframe
            src={viewerUrl}
            style={{
              width: '100%',
              height: '100%',
              border: 'none',
              borderRadius: '0 0 12px 12px',
            }}
            title={documentName}
          />
        );
      }
      case 'image':
        return (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '100%',
            height: '100%',
            overflow: 'auto',
            padding: '1rem',
          }}>
            <img
              src={fileUrl}
              alt={documentName}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain',
                borderRadius: 8,
              }}
            />
          </div>
        );
      default:
        return (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            gap: '1rem',
            color: 'var(--text-secondary)',
          }}>
            <Document size={48} />
            <p>此檔案類型不支援線上預覽</p>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '0.5rem 1rem',
                background: 'var(--primary)',
                color: 'white',
                borderRadius: 8,
                textDecoration: 'none',
                fontSize: '0.875rem',
              }}
            >
              下載檔案
            </a>
          </div>
        );
    }
  };

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '90vw',
          height: '85vh',
          maxWidth: 1100,
          background: 'var(--bg-secondary, #fff)',
          borderRadius: 12,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.75rem 1.25rem',
          borderBottom: '1px solid var(--border, #e0e0e0)',
          background: 'var(--bg-tertiary, #f4f4f4)',
          flexShrink: 0,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.9375rem',
            fontWeight: 600,
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            <Document size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            {documentName}
          </div>
          <button
            onClick={onClose}
            style={{
              width: 32,
              height: 32,
              border: 'none',
              background: 'transparent',
              borderRadius: 8,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-secondary)',
              flexShrink: 0,
            }}
            title="關閉"
          >
            <Close size={20} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {renderContent()}
        </div>
      </div>
    </div>,
    document.body
  );
}

export default function SourcePreview({ documentId, documentName }: SourcePreviewProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleOpen = useCallback(() => {
    if (!documentId) {
      alert('無法預覽：缺少文件識別碼');
      return;
    }
    setIsOpen(true);
  }, [documentId]);

  const handleClose = useCallback(() => setIsOpen(false), []);

  if (!documentId) return null;

  return (
    <>
      <button
        className="source-preview-btn"
        onClick={handleOpen}
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

      {isOpen && (
        <PreviewModal
          documentId={documentId}
          documentName={documentName}
          onClose={handleClose}
        />
      )}
    </>
  );
}
