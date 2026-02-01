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
  InProgress
} from '@carbon/icons-react';
import { UploadProgress } from '@/components/upload/UploadProgress';
import type { ProgressMessage } from '@/hooks/useUploadProgress';

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
      const res = await fetch(`${API_BASE}/api/kb/documents`);
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
      console.error('Failed to fetch documents:', error);
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
        const res = await fetch(`${API_BASE}/api/kb/upload`, {
          method: 'POST',
          body: formData,
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
        const res = await fetch(`${API_BASE}/api/kb/documents/${id}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          setDocuments(documents.filter(doc => doc.id !== id));
        } else {
          const error = await res.json();
          alert(`刪除失敗: ${error.detail}`);
        }
      } catch (error) {
        console.error('Delete error:', error);
        alert('刪除失敗，請稍後再試');
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

  return (
    <div className="settings-container" style={{ maxWidth: 1000 }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '1.5rem'
      }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 600 }}>
          知識庫管理
        </h1>
      </div>

      {/* Upload Area */}
      <div
        className={`settings-section ${dragOver ? 'drag-over' : ''}`}
        style={{
          border: dragOver ? '2px dashed var(--primary)' : '2px dashed var(--border)',
          background: dragOver ? 'var(--primary-subtle)' : 'var(--bg-primary)',
          textAlign: 'center',
          padding: '2rem',
          cursor: uploading ? 'default' : 'pointer',
          transition: 'all 0.2s',
          opacity: uploading ? 0.7 : 1,
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={(e) => handleFileSelect(e.target.files)}
          accept=".pdf,.docx,.png,.jpg,.jpeg,.webp"
          multiple
          style={{ display: 'none' }}
          disabled={uploading}
        />
        <CloudUpload size={48} style={{ color: 'var(--primary)', marginBottom: '1rem' }} />
        <div style={{ fontSize: '1.125rem', fontWeight: 500, marginBottom: '0.5rem' }}>
          {uploading ? '上傳中...' : '拖放文件到這裡上傳'}
        </div>
        <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          支援 PDF、Word (.docx)、PNG、JPG、WEBP 格式
        </div>
        <button
          className="btn btn-primary"
          style={{ marginTop: '1rem' }}
          onClick={(e) => {
            e.stopPropagation();
            fileInputRef.current?.click();
          }}
          disabled={uploading}
        >
          <Upload size={16} />
          {uploading ? '處理中...' : '選擇檔案'}
        </button>
      </div>

      {/* Upload Progress (WebSocket) */}
      {activeTaskId && (
        <UploadProgress
          taskId={activeTaskId}
          onComplete={handleUploadComplete}
          onError={handleUploadError}
          className="mt-4"
        />
      )}

      {/* Stats */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(4, 1fr)', 
        gap: '1rem',
        marginBottom: '1.5rem'
      }}>
        {[
          { label: '文件數量', value: documents.length, unit: '份' },
          { label: '知識片段', value: totalChunks, unit: '個' },
          { label: '總大小', value: formatSize(totalSize), unit: '' },
          { label: '處理中', value: documents.filter(d => d.status === 'processing').length, unit: '份' },
        ].map((stat) => (
          <div key={stat.label} className="settings-section" style={{ textAlign: 'center', padding: '1rem' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--primary)' }}>
              {stat.value}{stat.unit}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              {stat.label}
            </div>
          </div>
        ))}
      </div>

      {/* Search */}
      <div className="settings-section" style={{ padding: '1rem' }}>
        <div style={{ position: 'relative' }}>
          <Search 
            size={18} 
            style={{ 
              position: 'absolute', 
              left: 12, 
              top: '50%', 
              transform: 'translateY(-50%)',
              color: 'var(--text-secondary)'
            }} 
          />
          <input
            type="text"
            className="form-input"
            placeholder="搜尋文件..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ paddingLeft: 40 }}
          />
        </div>
      </div>

      {/* Document List */}
      <div className="settings-section" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>文件名稱</th>
              <th>類型</th>
              <th>大小</th>
              <th>知識片段</th>
              <th>狀態</th>
              <th>上傳時間</th>
              <th style={{ width: 80 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {filteredDocuments.map((doc) => (
              <tr key={doc.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    {doc.type === 'pdf' ? (
                      <Document size={20} style={{ color: '#da1e28' }} />
                    ) : (
                      <ImageIcon size={20} style={{ color: '#0043ce' }} />
                    )}
                    <span style={{ 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      whiteSpace: 'nowrap',
                      maxWidth: 200
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
                <td>{formatSize(doc.size)}</td>
                <td>{doc.chunks || '-'}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {doc.status === 'ready' && (
                      <>
                        <CheckmarkFilled size={16} style={{ color: '#198038' }} />
                        <span style={{ color: '#198038' }}>就緒</span>
                      </>
                    )}
                    {doc.status === 'processing' && (
                      <>
                        <InProgress size={16} style={{ color: '#0043ce' }} className="spinner" />
                        <span style={{ color: '#0043ce' }}>處理中</span>
                      </>
                    )}
                    {doc.status === 'error' && (
                      <>
                        <ErrorFilled size={16} style={{ color: '#da1e28' }} />
                        <span style={{ color: '#da1e28' }}>錯誤</span>
                      </>
                    )}
                  </div>
                </td>
                <td>{doc.uploadedAt.toLocaleDateString('zh-TW')}</td>
                <td>
                  <button 
                    className="input-btn" 
                    title="刪除"
                    onClick={() => handleDelete(doc.id)}
                    style={{ color: '#da1e28' }}
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
            padding: '3rem',
            textAlign: 'center',
            color: 'var(--text-secondary)'
          }}>
            <InProgress size={24} className="spinner" style={{ marginBottom: '0.5rem' }} />
            <div>載入中...</div>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div style={{
            padding: '3rem',
            textAlign: 'center',
            color: 'var(--text-secondary)'
          }}>
            {documents.length === 0 ? '尚無上傳文件，請上傳文件開始建立知識庫' : '找不到符合的文件'}
          </div>
        ) : null}
      </div>

      {/* Info */}
      <div style={{ 
        marginTop: '1.5rem',
        padding: '1rem',
        background: '#edf5ff',
        borderRadius: 8,
        fontSize: '0.875rem',
        color: '#0043ce',
      }}>
        <strong>💡 提示：</strong>上傳 PDF 文件會自動提取文字和圖片，建立多模態知識庫索引。圖片會使用 CLIP 模型進行視覺嵌入。
      </div>
    </div>
  );
}
