'use client';

import { useState } from 'react';
import { Chat, TrashCan, Search, Calendar, Filter } from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import { Conversation } from '@/types';

export default function HistoryPage() {
  const { conversations, setActiveConversation } = useStore();
  const [search, setSearch] = useState('');
  const [dateFilter, setDateFilter] = useState<'all' | 'today' | 'week' | 'month'>('all');

  const filterByDate = (conv: Conversation) => {
    const now = new Date();
    const convDate = new Date(conv.updatedAt);
    
    switch (dateFilter) {
      case 'today':
        return convDate.toDateString() === now.toDateString();
      case 'week':
        const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        return convDate >= weekAgo;
      case 'month':
        const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        return convDate >= monthAgo;
      default:
        return true;
    }
  };

  const filteredConversations = conversations
    .filter(conv => 
      conv.title.toLowerCase().includes(search.toLowerCase()) ||
      conv.messages.some(m => m.content.toLowerCase().includes(search.toLowerCase()))
    )
    .filter(filterByDate)
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  const handleSelect = (id: string) => {
    setActiveConversation(id);
    window.location.href = '/chat';
  };

  const formatDate = (date: Date) => {
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) return '今天 ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
    if (days === 1) return '昨天';
    if (days < 7) return `${days} 天前`;
    return d.toLocaleDateString('zh-TW');
  };

  return (
    <div className="settings-container" style={{ maxWidth: 900 }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1.5rem' }}>
        對話歷史
      </h1>

      {/* Search and Filter */}
      <div className="settings-section" style={{ padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
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
              placeholder="搜尋對話內容..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ paddingLeft: 40 }}
            />
          </div>
          
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {[
              { value: 'all', label: '全部' },
              { value: 'today', label: '今天' },
              { value: 'week', label: '本週' },
              { value: 'month', label: '本月' },
            ].map((filter) => (
              <button
                key={filter.value}
                className={`btn ${dateFilter === filter.value ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setDateFilter(filter.value as any)}
                style={{ padding: '0.5rem 1rem' }}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Conversation List */}
      <div className="settings-section" style={{ padding: 0 }}>
        {filteredConversations.length === 0 ? (
          <div style={{ 
            padding: '4rem', 
            textAlign: 'center', 
            color: 'var(--text-secondary)' 
          }}>
            <Chat size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
            <p>{conversations.length === 0 ? '尚無對話記錄' : '找不到符合的對話'}</p>
          </div>
        ) : (
          filteredConversations.map((conv, index) => (
            <div
              key={conv.id}
              onClick={() => handleSelect(conv.id)}
              style={{
                padding: '1rem 1.5rem',
                borderBottom: index < filteredConversations.length - 1 ? '1px solid var(--border)' : 'none',
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-secondary)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: 8,
                  background: 'var(--bg-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0
                }}>
                  <Chat size={20} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ 
                    fontWeight: 500, 
                    marginBottom: '0.25rem',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {conv.title}
                  </div>
                  <div style={{ 
                    fontSize: '0.875rem', 
                    color: 'var(--text-secondary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {conv.messages.length > 0 
                      ? conv.messages[conv.messages.length - 1].content.slice(0, 100)
                      : '空對話'}
                  </div>
                </div>
                <div style={{ 
                  fontSize: '0.75rem', 
                  color: 'var(--text-secondary)',
                  whiteSpace: 'nowrap'
                }}>
                  {formatDate(conv.updatedAt)}
                </div>
              </div>
              <div style={{ 
                marginTop: '0.5rem', 
                marginLeft: '3.5rem',
                fontSize: '0.75rem',
                color: 'var(--text-placeholder)'
              }}>
                {conv.messages.length} 則訊息
              </div>
            </div>
          ))
        )}
      </div>

      {/* Stats */}
      <div style={{ 
        marginTop: '1.5rem',
        padding: '1rem',
        background: 'var(--bg-secondary)',
        borderRadius: 8,
        fontSize: '0.875rem',
        color: 'var(--text-secondary)',
        textAlign: 'center'
      }}>
        共 {conversations.length} 個對話，{conversations.reduce((acc, c) => acc + c.messages.length, 0)} 則訊息
      </div>
    </div>
  );
}
