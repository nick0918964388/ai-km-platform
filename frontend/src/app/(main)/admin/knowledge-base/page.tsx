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
  Time,
  View,
  Close,
  Checkbox,
  CheckboxCheckedFilled,
  Minimize,
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
  currentVersion?: number;
}

interface VersionRecord {
  id: number;
  document_id: string;
  version: number;
  filename: string;
  file_size: number;
  chunk_count: number;
  file_hash: string | null;
  change_note: string | null;
  uploaded_by: string | null;
  created_at: string;
}

interface UploadQueueItem {
  file: File;
  taskId?: string;
  documentId?: string;
  status: 'pending' | 'uploading' | 'processing' | 'done' | 'error';
  progress?: number;
  error?: string;
  chunks?: number;
}

const API_BASE = API_URL;

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [search, setSearch] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [versionHistoryId, setVersionHistoryId] = useState<string | null>(null);
  const [versionRecords, setVersionRecords] = useState<VersionRecord[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [uploadQueue, setUploadQueue] = useState<UploadQueueItem[]>([]);
  const [previewModal, setPreviewModal] = useState<{ docId: string; name: string; content: string } | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [uploadMinimized, setUploadMinimized] = useState(false);
  const isProcessingQueue = useRef(false);
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
            currentVersion: doc.current_version || 1,
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
    setDocuments(prev =>
      prev.map(doc =>
        doc.taskId === message.task_id
          ? { ...doc, status: 'ready', chunks: message.chunk_count || 0 }
          : doc
      )
    );
    // Update queue item for this task
    setUploadQueue(prev => prev.map(item =>
      item.taskId === message.task_id
        ? { ...item, status: 'done', progress: 100, chunks: message.chunk_count || 0 }
        : item
    ));
    setActiveTaskId(null);
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUploadError = useCallback((error: string) => {
    setDocuments(prev =>
      prev.map(doc =>
        doc.taskId === activeTaskId
          ? { ...doc, status: 'error' }
          : doc
      )
    );
    setUploadQueue(prev => prev.map(item =>
      item.taskId === activeTaskId
        ? { ...item, status: 'error', error }
        : item
    ));
    setActiveTaskId(null);
    console.error('Upload error:', error);
  }, [activeTaskId]);

  const processQueue = useCallback(async (queue: UploadQueueItem[]) => {
    if (isProcessingQueue.current) return;
    isProcessingQueue.current = true;
    setUploading(true);

    for (let i = 0; i < queue.length; i++) {
      const item = queue[i];
      if (item.status !== 'pending') continue;

      // Update status to uploading
      setUploadQueue(prev => prev.map(q =>
        q.file === item.file && q.status === 'pending'
          ? { ...q, status: 'uploading', progress: 10 }
          : q
      ));

      const formData = new FormData();
      formData.append('file', item.file);

      try {
        // Show progress bump for upload start
        setUploadQueue(prev => prev.map(q =>
          q.file === item.file && q.status === 'uploading'
            ? { ...q, progress: 30 }
            : q
        ));

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

        // Upload+processing completed (synchronous endpoint)
        setUploadQueue(prev => prev.map(q =>
          q.file === item.file
            ? { ...q, status: 'done', progress: 100, chunks: result.chunk_count, documentId: result.document_id }
            : q
        ));

        const newDoc: KBDocument = {
          id: result.document_id,
          name: item.file.name,
          type: result.doc_type,
          size: item.file.size,
          uploadedAt: new Date(),
          status: 'ready',
          chunks: result.chunk_count,
        };

        setDocuments(prev => [newDoc, ...prev]);
      } catch (error) {
        console.error('Upload error:', error);
        setUploadQueue(prev => prev.map(q =>
          q.file === item.file
            ? { ...q, status: 'error', error: getErrorMessage(error) }
            : q
        ));
      }
    }

    setUploading(false);
    isProcessingQueue.current = false;
    fetchDocuments();
  }, [fetchDocuments]);

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newItems: UploadQueueItem[] = Array.from(files).map(file => ({
      file,
      status: 'pending' as const,
      progress: 0,
    }));

    setUploadQueue(prev => [...prev, ...newItems]);
    processQueue(newItems);
  };

  const handlePreview = async (doc: KBDocument) => {
    if (doc.type === 'pdf') {
      window.open(`${API_BASE}/api/kb/documents/${doc.id}/file`, '_blank');
      return;
    }
    setLoadingPreview(true);
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/kb/documents/${doc.id}/preview`, {
        headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
        timeout: TIMEOUTS.DEFAULT,
      });
      if (res.ok) {
        const data = await res.json();
        setPreviewModal({ docId: doc.id, name: doc.name, content: data.preview || '(無內容)' });
      } else {
        setPreviewModal({ docId: doc.id, name: doc.name, content: '無法載入預覽內容' });
      }
    } catch {
      setPreviewModal({ docId: doc.id, name: doc.name, content: '載入失敗' });
    } finally {
      setLoadingPreview(false);
    }
  };

  const clearCompletedUploads = () => {
    setUploadQueue(prev => prev.filter(q => q.status !== 'done' && q.status !== 'error'));
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

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredDocuments.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredDocuments.map(d => d.id)));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`確定要刪除選取的 ${selectedIds.size} 筆文件？相關的知識庫內容也會被移除。`)) return;
    setBatchDeleting(true);
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/kb/documents/batch-delete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        },
        body: JSON.stringify({ document_ids: Array.from(selectedIds) }),
        timeout: TIMEOUTS.DEFAULT,
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(prev => prev.filter(d => !selectedIds.has(d.id)));
        setSelectedIds(new Set());
        if (data.failed?.length > 0) {
          alert(`${data.message}`);
        }
      } else {
        const error = await res.json();
        alert(`批次刪除失敗: ${error.detail}`);
      }
    } catch (error) {
      alert(getErrorMessage(error));
    } finally {
      setBatchDeleting(false);
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

  const toggleVersionHistory = async (docId: string) => {
    if (versionHistoryId === docId) {
      setVersionHistoryId(null);
      setVersionRecords([]);
      return;
    }
    setVersionHistoryId(docId);
    setLoadingVersions(true);
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/kb/documents/${docId}/versions`, {
        headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
        timeout: TIMEOUTS.DEFAULT,
      });
      if (res.ok) {
        const data = await res.json();
        setVersionRecords(data.versions || []);
      }
    } catch (error) {
      console.error('Failed to fetch versions:', getErrorMessage(error));
      setVersionRecords([]);
    } finally {
      setLoadingVersions(false);
    }
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
        {selectedIds.size > 0 && (
          <button
            onClick={handleBatchDelete}
            disabled={batchDeleting}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0 1.25rem',
              height: 48,
              background: 'var(--error)',
              color: 'white',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: batchDeleting ? 'wait' : 'pointer',
              fontWeight: 600,
              fontSize: '0.875rem',
              opacity: batchDeleting ? 0.7 : 1,
            }}
          >
            <TrashCan size={16} />
            {batchDeleting ? '刪除中...' : `刪除 (${selectedIds.size})`}
          </button>
        )}
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
          accept=".pdf,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp"
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

      {/* Hidden WebSocket tracker for active task */}
      {activeTaskId && (
        <div style={{ display: 'none' }}>
          <UploadProgress
            taskId={activeTaskId}
            onComplete={handleUploadComplete}
            onError={handleUploadError}
          />
        </div>
      )}

      {/* Floating Upload Queue Progress Panel */}
      {uploadQueue.length > 0 && (
        <div style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          width: uploadMinimized ? 280 : 420,
          maxHeight: uploadMinimized ? 'auto' : '50vh',
          padding: uploadMinimized ? '0.75rem 1rem' : '1rem 1.25rem',
          background: 'var(--bg-primary)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          zIndex: 900,
          overflow: uploadMinimized ? 'hidden' : 'auto',
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: uploadMinimized ? 0 : '0.75rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {uploading && <InProgress size={16} style={{ color: 'var(--accent)' }} className="spinner" />}
              {!uploading && <CloudUpload size={16} style={{ color: 'var(--accent)' }} />}
              <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.8125rem' }}>
                {uploading ? `上傳中 (${uploadQueue.filter(q => q.status === 'done').length}/${uploadQueue.length})` : `上傳完成 (${uploadQueue.length})`}
              </span>
            </div>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              <button
                onClick={() => setUploadMinimized(!uploadMinimized)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}
                title={uploadMinimized ? '展開' : '最小化'}
              >
                <Minimize size={14} />
              </button>
              {uploadQueue.every(q => q.status === 'done' || q.status === 'error') && (
                <button
                  onClick={clearCompletedUploads}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 2 }}
                  title="關閉"
                >
                  <Close size={14} />
                </button>
              )}
            </div>
          </div>
          {!uploadMinimized && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {uploadQueue.map((item, idx) => (
                <div key={`${item.file.name}-${idx}`} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.5rem 0',
                  borderBottom: idx < uploadQueue.length - 1 ? '1px solid var(--border)' : 'none',
                }}>
                  <div style={{ flexShrink: 0, width: 20, textAlign: 'center' }}>
                    {item.status === 'done' && <CheckmarkFilled size={16} style={{ color: 'var(--success)' }} />}
                    {item.status === 'error' && <ErrorFilled size={16} style={{ color: 'var(--error)' }} />}
                    {item.status === 'pending' && <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>...</span>}
                    {(item.status === 'uploading' || item.status === 'processing') && (
                      <InProgress size={16} style={{ color: 'var(--accent)' }} className="spinner" />
                    )}
                  </div>
                  <span style={{
                    flex: 1,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontSize: '0.8125rem',
                    color: 'var(--text-primary)',
                    fontWeight: 500,
                  }}>
                    {item.file.name}
                  </span>
                  <span style={{
                    fontSize: '0.75rem',
                    color: item.status === 'error' ? 'var(--error)' : item.status === 'done' ? 'var(--success)' : 'var(--text-muted)',
                    flexShrink: 0,
                  }}>
                    {item.status === 'pending' && '等待中'}
                    {item.status === 'uploading' && '上傳中...'}
                    {item.status === 'processing' && '向量化中...'}
                    {item.status === 'done' && `✓ ${item.chunks || 0} 切片`}
                    {item.status === 'error' && (item.error || '失敗')}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Document Table */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 40, textAlign: 'center', padding: '0.5rem' }}>
                <button
                  onClick={toggleSelectAll}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: 4,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: selectedIds.size === filteredDocuments.length && filteredDocuments.length > 0
                      ? 'var(--accent)' : 'var(--text-muted)',
                  }}
                  title={selectedIds.size === filteredDocuments.length ? '取消全選' : '全選'}
                >
                  {selectedIds.size === filteredDocuments.length && filteredDocuments.length > 0
                    ? <CheckboxCheckedFilled size={18} />
                    : <Checkbox size={18} />}
                </button>
              </th>
              <th>文件名稱</th>
              <th>類型</th>
              <th>大小</th>
              <th>知識片段</th>
              <th>狀態</th>
              <th>上傳時間</th>
              <th style={{ width: 110, textAlign: 'center' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {paginatedDocuments.map((doc) => [
              <tr key={doc.id} style={{ background: selectedIds.has(doc.id) ? 'rgba(0, 95, 158, 0.05)' : undefined }}>
                <td style={{ textAlign: 'center', padding: '0.5rem' }}>
                  <button
                    onClick={() => toggleSelect(doc.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 4,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: selectedIds.has(doc.id) ? 'var(--accent)' : 'var(--text-muted)',
                    }}
                  >
                    {selectedIds.has(doc.id)
                      ? <CheckboxCheckedFilled size={18} />
                      : <Checkbox size={18} />}
                  </button>
                </td>
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
                    <button
                      onClick={() => handlePreview(doc)}
                      title={doc.type === 'pdf' ? '在新分頁預覽 PDF' : '預覽文件內容'}
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: 240,
                        color: 'var(--accent)',
                        fontWeight: 500,
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        padding: 0,
                        textAlign: 'left',
                        fontSize: 'inherit',
                        textDecoration: 'underline',
                        textDecorationColor: 'transparent',
                        transition: 'text-decoration-color 0.2s',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.textDecorationColor = 'var(--accent)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.textDecorationColor = 'transparent'; }}
                    >
                      {doc.name}
                    </button>
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
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}>
                    <button
                      className="btn-icon"
                      title="預覽"
                      onClick={() => handlePreview(doc)}
                      style={{ color: 'var(--accent)' }}
                    >
                      <View size={16} />
                    </button>
                    <button
                      onClick={() => toggleVersionHistory(doc.id)}
                      style={{
                        background: versionHistoryId === doc.id ? 'var(--accent)' : 'var(--bg-secondary)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)',
                        cursor: 'pointer',
                        fontSize: '0.7rem',
                        color: versionHistoryId === doc.id ? 'white' : 'var(--text-muted)',
                        padding: '2px 6px',
                        fontWeight: 600,
                        lineHeight: 1.4,
                      }}
                      title="版本歷史"
                    >
                      v{doc.currentVersion || 1}
                    </button>
                    <button
                      className="btn-icon"
                      title="刪除"
                      onClick={() => handleDelete(doc.id)}
                      style={{ color: 'var(--error)' }}
                      disabled={doc.status === 'processing'}
                    >
                      <TrashCan size={16} />
                    </button>
                  </div>
                </td>
              </tr>,
              versionHistoryId === doc.id && (
                <tr key={`${doc.id}-versions`}>
                  <td colSpan={8} style={{ padding: 0 }}>
                    <div style={{
                      background: 'var(--bg-secondary)',
                      borderTop: '1px solid var(--border)',
                      borderBottom: '1px solid var(--border)',
                      padding: '0.75rem 1.5rem',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <Time size={14} style={{ color: 'var(--text-muted)' }} />
                        <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          版本歷史
                        </span>
                      </div>
                      {loadingVersions ? (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>載入中...</div>
                      ) : versionRecords.length === 0 ? (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>v1 - 初始版本</div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                          {versionRecords.map((v) => (
                            <div key={v.id} style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '1rem',
                              fontSize: '0.8125rem',
                              color: 'var(--text-secondary)',
                            }}>
                              <span style={{ fontWeight: 600, color: 'var(--text-primary)', minWidth: 28 }}>v{v.version}</span>
                              <span style={{ color: 'var(--text-muted)' }}>{v.chunk_count} 片段</span>
                              <span style={{ color: 'var(--text-muted)' }}>{v.file_size ? formatSize(v.file_size) : '-'}</span>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                                {v.created_at ? new Date(v.created_at).toLocaleString('zh-TW') : '-'}
                              </span>
                              {v.change_note && (
                                <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>{v.change_note}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ),
            ])}
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

      {/* Preview Modal */}
      {previewModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setPreviewModal(null)}
        >
          <div
            style={{
              background: 'var(--bg-primary)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)',
              width: '90%',
              maxWidth: 640,
              maxHeight: '80vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '1rem 1.25rem',
              borderBottom: '1px solid var(--border)',
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                overflow: 'hidden',
              }}>
                <Document size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                <span style={{
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {previewModal.name}
                </span>
              </div>
              <button
                className="btn-icon"
                onClick={() => setPreviewModal(null)}
                style={{ flexShrink: 0 }}
              >
                <Close size={18} />
              </button>
            </div>
            {/* Modal Body */}
            <div style={{
              padding: '1.25rem',
              overflow: 'auto',
              flex: 1,
            }}>
              {loadingPreview ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                  <InProgress size={24} className="spinner" style={{ marginBottom: '0.5rem', color: 'var(--accent)' }} />
                  <div>載入中...</div>
                </div>
              ) : (
                <pre style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontSize: '0.8125rem',
                  lineHeight: 1.6,
                  color: 'var(--text-secondary)',
                  fontFamily: 'inherit',
                  margin: 0,
                }}>
                  {previewModal.content}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
