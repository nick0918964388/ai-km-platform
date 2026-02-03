'use client';

import { useState, useEffect, useCallback } from 'react';
import { Document, Close, Download } from '@carbon/icons-react';
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
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [mounted, setMounted] = useState(false);
  
  const fileUrl = `${API_URL}/api/kb/documents/${documentId}/file`;
  const previewType = getPreviewType(documentName);
  
  // Ensure client-side only rendering for portal
  useEffect(() => {
    setMounted(true);
  }, []);

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

  const handleIframeLoad = () => {
    setIsLoading(false);
  };

  const handleIframeError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  const handleImageLoad = () => {
    setIsLoading(false);
  };

  const handleImageError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  const renderContent = () => {
    if (hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          gap: '1rem',
          color: 'var(--text-secondary, #525252)',
        }}>
          <Document size={48} />
          <p>無法預覽此檔案</p>
          <a
            href={fileUrl}
            target="_blank"
            rel="noopener noreferrer"
            download
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 1rem',
              background: 'var(--primary, #0f62fe)',
              color: 'white',
              borderRadius: 8,
              textDecoration: 'none',
              fontSize: '0.875rem',
            }}
          >
            <Download size={16} />
            下載檔案
          </a>
        </div>
      );
    }

    switch (previewType) {
      case 'pdf':
        return (
          <>
            {isLoading && (
              <div style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--bg-secondary, #fff)',
              }}>
                <div style={{ textAlign: 'center', color: 'var(--text-secondary, #525252)' }}>
                  <div className="loading-spinner" style={{
                    width: 40,
                    height: 40,
                    border: '3px solid var(--border, #e0e0e0)',
                    borderTopColor: 'var(--primary, #0f62fe)',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 1rem',
                  }} />
                  <p>載入中...</p>
                </div>
              </div>
            )}
            <iframe
              src={fileUrl}
              style={{
                width: '100%',
                height: '100%',
                border: 'none',
                borderRadius: '0 0 12px 12px',
                display: isLoading ? 'none' : 'block',
              }}
              title={documentName}
              onLoad={handleIframeLoad}
              onError={handleIframeError}
            />
          </>
        );
      case 'word':
      case 'excel': {
        // For Word/Excel, offer direct download as Google Docs Viewer often fails
        return (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            gap: '1rem',
            color: 'var(--text-secondary, #525252)',
          }}>
            <Document size={48} />
            <p>Office 文件預覽</p>
            <p style={{ fontSize: '0.875rem', opacity: 0.7 }}>建議下載後使用本機軟體開啟</p>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              download
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                background: 'var(--primary, #0f62fe)',
                color: 'white',
                borderRadius: 8,
                textDecoration: 'none',
                fontSize: '0.875rem',
              }}
            >
              <Download size={16} />
              下載檔案
            </a>
          </div>
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
            position: 'relative',
          }}>
            {isLoading && (
              <div style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--bg-secondary, #fff)',
              }}>
                <div style={{ textAlign: 'center', color: 'var(--text-secondary, #525252)' }}>
                  <div style={{
                    width: 40,
                    height: 40,
                    border: '3px solid var(--border, #e0e0e0)',
                    borderTopColor: 'var(--primary, #0f62fe)',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 1rem',
                  }} />
                  <p>載入中...</p>
                </div>
              </div>
            )}
            <img
              src={fileUrl}
              alt={documentName}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain',
                borderRadius: 8,
                display: isLoading ? 'none' : 'block',
              }}
              onLoad={handleImageLoad}
              onError={handleImageError}
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
            color: 'var(--text-secondary, #525252)',
          }}>
            <Document size={48} />
            <p>此檔案類型不支援線上預覽</p>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              download
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                background: 'var(--primary, #0f62fe)',
                color: 'white',
                borderRadius: 8,
                textDecoration: 'none',
                fontSize: '0.875rem',
              }}
            >
              <Download size={16} />
              下載檔案
            </a>
          </div>
        );
    }
  };

  if (!mounted) return null;
  
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
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
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
            color: 'var(--text-primary, #161616)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}>
            <Document size={18} style={{ color: 'var(--accent, #0f62fe)', flexShrink: 0 }} />
            {documentName}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              download
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
                color: 'var(--text-secondary, #525252)',
                textDecoration: 'none',
              }}
              title="下載"
            >
              <Download size={18} />
            </a>
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
                color: 'var(--text-secondary, #525252)',
                flexShrink: 0,
              }}
              title="關閉"
            >
              <Close size={20} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
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
