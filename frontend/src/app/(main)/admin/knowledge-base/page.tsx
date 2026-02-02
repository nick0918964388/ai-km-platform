'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Upload,
  Document,
  Image as ImageIcon,
  TrashCan,
  Search,
  CloudUpload,
  CheckmarkFilled,
  ErrorFilled,
  InProgress,
  DataBase,
  ChevronLeft,
  ChevronRight,
  Notification,
} from '@carbon/icons-react';
import { UploadProgress } from '@/components/upload/UploadProgress';
import type { ProgressMessage } from '@/hooks/useUploadProgress';
import { API_URL, API_KEY, TIMEOUTS, fetchWithTimeout, getErrorMessage } from '@/lib/api';

interface KBDocument {
  id: string;
  name: string;
  type: 'pdf' | 'image' | 'word';
  size: number;
  uploadedAt: Date;
  status: 'processing' | 'ready' | 'error';
  chunks?: number;
  taskId?: string;
}

const API_BASE = API_URL;

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [search, setSearch] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch documents from API on mount
  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/kb/documents`, {
        headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
        timeout: TIMEOUTS.DEFAULT,
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(
          data.documents.map((doc: any) => ({
            id: doc.id,
            name: doc.filename,
            type: doc.doc_type,
            size: doc.file_size,
            uploadedAt: new Date(doc.uploaded_at),
            status: 'ready',
            chunks: doc.chunk_count,
          }))
        );
      }
    } catch (error) {
      console.error('Failed to fetch documents:', getErrorMessage(error));
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const filteredDocuments = documents.filter(doc =>
    doc.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleUploadComplete = useCallback((message: ProgressMessage) => {
    // Update document status on completion
    setDocuments(prev =>
      prev.map(doc =>
        doc.taskId === message.task_id
          ? { ...doc, status: 'ready', chunks: message.chunk_count || 0 }
          : doc
      )
    );
    setActiveTaskId(null);
    // Refresh document list from server
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUploadError = useCallback((error: string) => {
    // Update document status on error
    setDocuments(prev =>
      prev.map(doc =>
        doc.taskId === activeTaskId
          ? { ...doc, status: 'error' }
          : doc
      )
    );
    setActiveTaskId(null);
    console.error('Upload error:', error);
  }, [activeTaskId]);

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploading(true);

    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetchWithTimeout(`${API_BASE}/api/kb/upload`, {
          method: 'POST',
          headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
          body: formData,
          timeout: TIMEOUTS.UPLOAD,
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || 'Upload failed');
        }

        const result = await res.json();

        // Add document to list
        const newDoc: KBDocument = {
          id: result.document_id,
          name: file.name,
          type: result.doc_type,
          size: file.size,
          uploadedAt: new Date(),
          status: 'ready',
          chunks: result.chunk_count,
          taskId: result.task_id,
        };

        setDocuments(prev => [newDoc, ...prev]);

        // If there's a task ID, track progress via WebSocket
        if (result.task_id) {
          setActiveTaskId(result.task_id);
          // Update doc status to processing
          setDocuments(prev =>
            prev.map(doc =>
              doc.id === result.document_id
                ? { ...doc, status: 'processing', taskId: result.task_id }
                : doc
            )
          );
        }
      } catch (error) {
        console.error('Upload error:', error);
        // Could add error state to document here
      }
    }

    setUploading(false);
  };

  const handleDelete = async (id: string) => {
    if (confirm('確定要刪除此文件？相關的知識庫內容也會被移除。')) {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/api/kb/documents/${id}`, {
          method: 'DELETE',
          headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
          timeout: TIMEOUTS.DEFAULT,
        });
        if (res.ok) {
          setDocuments(documents.filter(doc => doc.id !== id));
        } else {
          const error = await res.json();
          alert(`刪除失敗: ${error.detail}`);
        }
      } catch (error) {
        console.error('Delete error:', error);
        alert(getErrorMessage(error));
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const totalChunks = documents.filter(d => d.status === 'ready').reduce((acc, d) => acc + (d.chunks || 0), 0);
  const totalSize = documents.reduce((acc, d) => acc + d.size, 0);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;
  const totalPages = Math.ceil(filteredDocuments.length / itemsPerPage);
  const paginatedDocuments = filteredDocuments.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div style={{
      padding: '2rem',
      height: '100%',
      overflow: 'auto',
      background: 'var(--bg-primary)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '1.5rem'
      }}>
        <div>
          <h1 style={{
            fontSize: '1.75rem',
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: '0.25rem'
          }}>
            知識庫管理
          </h1>
          <p style={{
            fontSize: '0.875rem',
            color: 'var(--text-muted)'
          }}>
            管理維修手冊、技術文件及知識庫內容
          </p>
        </div>
        <button className="btn-icon">
          <Notification size={20} />
        </button>
      </div>

      {/* Stats Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '1.25rem',
        marginBottom: '1.5rem'
      }}>
        <div className="stat-card">
          <div className="stat-card-header">
            <span className="stat-card-title">文件數量</span>
            <div className="stat-card-icon" style={{ background: 'var(--primary-light)' }}>
              <Document size={20} style={{ color: 'var(--accent)' }} />
            </div>
          </div>
          <div className="stat-card-value">{documents.length}</div>
          <div className="stat-card-change neutral">總計上傳文件</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-header">
            <span className="stat-card-title">知識片段</span>
            <div className="stat-card-icon" style={{ background: 'var(--primary-light)' }}>
              <DataBase size={20} style={{ color: 'var(--accent)' }} />
            </div>
          </div>
          <div className="stat-card-value">{totalChunks.toLocaleString()}</div>
          <div className="stat-card-change neutral">已建立索引</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-header">
            <span className="stat-card-title">儲存空間</span>
            <div className="stat-card-icon" style={{ background: 'var(--primary-light)' }}>
              <CloudUpload size={20} style={{ color: 'var(--accent)' }} />
            </div>
          </div>
          <div className="stat-card-value">{formatSize(totalSize)}</div>
          <div className="stat-card-change neutral">已使用空間</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-header">
            <span className="stat-card-title">處理中</span>
            <div className="stat-card-icon" style={{ background: 'var(--warning-light)' }}>
              <InProgress size={20} style={{ color: 'var(--warning)' }} />
            </div>
          </div>
          <div className="stat-card-value">{documents.filter(d => d.status === 'processing').length}</div>
          <div className="stat-card-change neutral">等待完成</div>
        </div>
      </div>

      {/* Search and Upload Row */}
      <div style={{
        display: 'flex',
        gap: '1rem',
        marginBottom: '1.5rem'
      }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Search
            size={18}
            style={{
              position: 'absolute',
              left: 16,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-muted)'
            }}
          />
          <input
            type="text"
            className="form-input"
            placeholder="搜尋文件名稱..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
            style={{
              paddingLeft: 48,
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              height: 48
            }}
          />
        </div>
        <button
          className="btn-primary"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0 1.5rem',
            height: 48
          }}
        >
          <Upload size={18} />
          上傳文件
        </button>
        <input
          type="file"
          ref={fileInputRef}
          onChange={(e) => handleFileSelect(e.target.files)}
          accept=".pdf,.docx,.png,.jpg,.jpeg,.webp"
          multiple
          style={{ display: 'none' }}
          disabled={uploading}
        />
      </div>

      {/* Upload Drop Zone (shown when dragging) */}
      {dragOver && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 51, 102, 0.9)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <CloudUpload size={64} style={{ color: 'var(--accent)', marginBottom: '1rem' }} />
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'white', marginBottom: '0.5rem' }}>
            放開以上傳文件
          </div>
          <div style={{ color: 'var(--text-muted)' }}>
            支援 PDF、Word、PNG、JPG、WEBP 格式
          </div>
        </div>
      )}

      {/* Upload Progress (WebSocket) */}
      {activeTaskId && (
        <UploadProgress
          taskId={activeTaskId}
          onComplete={handleUploadComplete}
          onError={handleUploadError}
          className="mt-4"
        />
      )}

      {/* Document Table */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>文件名稱</th>
              <th>類型</th>
              <th>大小</th>
              <th>知識片段</th>
              <th>狀態</th>
              <th>上傳時間</th>
              <th style={{ width: 80, textAlign: 'center' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {paginatedDocuments.map((doc) => (
              <tr key={doc.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{
                      width: 36,
                      height: 36,
                      borderRadius: 'var(--radius-md)',
                      background: doc.type === 'pdf' ? 'rgba(218, 30, 40, 0.15)' : 'rgba(80, 144, 211, 0.15)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0
                    }}>
                      {doc.type === 'pdf' ? (
                        <Document size={18} style={{ color: '#ff6b6b' }} />
                      ) : (
                        <ImageIcon size={18} style={{ color: 'var(--accent)' }} />
                      )}
                    </div>
                    <span style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: 240,
                      color: 'var(--text-primary)',
                      fontWeight: 500
                    }}>
                      {doc.name}
                    </span>
                  </div>
                </td>
                <td>
                  <span className={`badge ${doc.type === 'pdf' ? 'badge-admin' : 'badge-user'}`}>
                    {doc.type.toUpperCase()}
                  </span>
                </td>
                <td style={{ color: 'var(--text-muted)' }}>{formatSize(doc.size)}</td>
                <td style={{ color: 'var(--text-muted)' }}>{doc.chunks || '-'}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {doc.status === 'ready' && (
                      <>
                        <CheckmarkFilled size={16} style={{ color: 'var(--success)' }} />
                        <span style={{ color: 'var(--success)', fontSize: '0.8125rem' }}>就緒</span>
                      </>
                    )}
                    {doc.status === 'processing' && (
                      <>
                        <InProgress size={16} style={{ color: 'var(--accent)' }} className="spinner" />
                        <span style={{ color: 'var(--accent)', fontSize: '0.8125rem' }}>處理中</span>
                      </>
                    )}
                    {doc.status === 'error' && (
                      <>
                        <ErrorFilled size={16} style={{ color: 'var(--error)' }} />
                        <span style={{ color: 'var(--error)', fontSize: '0.8125rem' }}>錯誤</span>
                      </>
                    )}
                  </div>
                </td>
                <td style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                  {doc.uploadedAt.toLocaleDateString('zh-TW')}
                </td>
                <td style={{ textAlign: 'center' }}>
                  <button
                    className="btn-icon"
                    title="刪除"
                    onClick={() => handleDelete(doc.id)}
                    style={{ color: 'var(--error)' }}
                    disabled={doc.status === 'processing'}
                  >
                    <TrashCan size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {loadingDocs ? (
          <div style={{
            padding: '4rem',
            textAlign: 'center',
            color: 'var(--text-muted)'
          }}>
            <InProgress size={32} className="spinner" style={{ marginBottom: '1rem', color: 'var(--accent)' }} />
            <div>載入文件列表中...</div>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div style={{
            padding: '4rem',
            textAlign: 'center',
            color: 'var(--text-muted)'
          }}>
            <DataBase size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
            <div style={{ marginBottom: '0.5rem', fontWeight: 500 }}>
              {documents.length === 0 ? '尚無上傳文件' : '找不到符合的文件'}
            </div>
            <div style={{ fontSize: '0.875rem' }}>
              {documents.length === 0 ? '點擊上方「上傳文件」按鈕開始建立知識庫' : '請嘗試其他搜尋關鍵字'}
            </div>
          </div>
        ) : null}

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--border)',
            background: 'var(--bg-secondary)'
          }}>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              顯示 {(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, filteredDocuments.length)} 筆，共 {filteredDocuments.length} 筆
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                className="btn-icon"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                style={{ opacity: currentPage === 1 ? 0.5 : 1 }}
              >
                <ChevronLeft size={18} />
              </button>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem'
              }}>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 'var(--radius-md)',
                      border: 'none',
                      background: page === currentPage ? 'var(--accent)' : 'transparent',
                      color: page === currentPage ? 'white' : 'var(--text-muted)',
                      fontWeight: page === currentPage ? 600 : 400,
                      cursor: 'pointer',
                      transition: 'all var(--transition-fast)'
                    }}
                  >
                    {page}
                  </button>
                ))}
              </div>
              <button
                className="btn-icon"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                style={{ opacity: currentPage === totalPages ? 0.5 : 1 }}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Info Banner */}
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem 1.25rem',
        background: 'var(--primary-light)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem'
      }}>
        <div style={{
          width: 32,
          height: 32,
          borderRadius: 'var(--radius-md)',
          background: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}>
          <DataBase size={16} style={{ color: 'white' }} />
        </div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          <strong style={{ color: 'var(--text-primary)' }}>提示：</strong>
          上傳 PDF 文件會自動提取文字和圖片，建立多模態知識庫索引。圖片會使用 CLIP 模型進行視覺嵌入。
        </div>
      </div>
    </div>
  );
}
