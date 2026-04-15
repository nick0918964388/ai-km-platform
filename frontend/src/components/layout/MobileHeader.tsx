'use client';

import { Menu, Close, Add, RecentlyViewed } from '@carbon/icons-react';
import { usePathname } from 'next/navigation';
import { useStore } from '@/store/useStore';
import { useState } from 'react';

export default function MobileHeader() {
  const { sidebarOpen, toggleSidebar, addConversation, conversations, setActiveConversation } = useStore();
  const pathname = usePathname();
  const isChat = pathname === '/chat' || pathname.startsWith('/chat/');
  const [historyOpen, setHistoryOpen] = useState(false);

  const handleNewChat = () => {
    const newConv = {
      id: Date.now().toString(),
      title: '新對話',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    addConversation(newConv);
    setHistoryOpen(false);
  };

  return (
    <div className="mobile-header">
      <button
        className="mobile-menu-btn"
        onClick={toggleSidebar}
        aria-label="Toggle menu"
      >
        {sidebarOpen ? <Close size={24} /> : <Menu size={24} />}
      </button>

      <div className="mobile-title">
        <span className="mobile-logo">KM</span>
        車輛維修知識庫
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
        {isChat && (
          <button
            className="mobile-menu-btn"
            onClick={() => setHistoryOpen(!historyOpen)}
            aria-label="歷史對話"
            style={{ position: 'relative' }}
          >
            <RecentlyViewed size={22} />
            {conversations.length > 0 && (
              <span style={{
                position: 'absolute',
                top: 4,
                right: 4,
                background: 'var(--accent)',
                color: 'white',
                borderRadius: '50%',
                fontSize: '0.5625rem',
                width: 16,
                height: 16,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
              }}>{conversations.length}</span>
            )}
          </button>
        )}
        <button
          className="mobile-menu-btn"
          onClick={handleNewChat}
          aria-label="New chat"
        >
          <Add size={24} />
        </button>
      </div>

      {/* Mobile history dropdown */}
      {isChat && historyOpen && (
        <div style={{
          position: 'absolute',
          top: 56,
          left: 0,
          right: 0,
          background: 'var(--bg-primary)',
          borderBottom: '1px solid var(--border)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
          zIndex: 101,
          maxHeight: '60vh',
          overflowY: 'auto',
        }}>
          <div style={{
            padding: '0.75rem 1rem',
            borderBottom: '1px solid var(--border)',
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            歷史對話
            <button
              onClick={() => setHistoryOpen(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}
            >
              <Close size={16} />
            </button>
          </div>
          {conversations.length === 0 ? (
            <div style={{ padding: '1.5rem', fontSize: '0.875rem', color: 'var(--text-muted)', textAlign: 'center' }}>
              尚無對話紀錄
            </div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => {
                  setActiveConversation(conv.id);
                  setHistoryOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  width: '100%',
                  padding: '0.875rem 1rem',
                  background: 'none',
                  border: 'none',
                  borderBottom: '1px solid var(--border)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  color: 'var(--text-primary)',
                  fontSize: '0.875rem',
                }}
              >
                <RecentlyViewed size={16} style={{ flexShrink: 0, color: 'var(--text-muted)' }} />
                <span style={{
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {conv.title}
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                  {new Date(conv.updatedAt).toLocaleDateString('zh-TW')}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
