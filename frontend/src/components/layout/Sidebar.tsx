'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Chat,
  Settings,
  UserMultiple,
  Add,
  Logout,
  Dashboard,
  RecentlyViewed,
  Locked,
  DataBase
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';

const navItems = [
  { href: '/chat', label: '對話', icon: Chat },
  { href: '/history', label: '對話歷史', icon: RecentlyViewed },
  { href: '/settings', label: '設定', icon: Settings },
];

const adminItems = [
  { href: '/admin/knowledge-base', label: '知識庫管理', icon: DataBase },
  { href: '/admin/users', label: '使用者管理', icon: UserMultiple },
  { href: '/admin/permissions', label: '權限管理', icon: Locked },
  { href: '/admin/dashboard', label: '儀表板', icon: Dashboard },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, setUser, conversations, addConversation, setActiveConversation, activeConversationId, toggleSidebar } = useStore();

  const handleLogout = () => {
    setUser(null);
    router.push('/login');
  };
  
  const handleNewChat = () => {
    const newConv = {
      id: Date.now().toString(),
      title: '新對話',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    addConversation(newConv);
    router.push('/chat');
    // Close sidebar on mobile after action
    if (window.innerWidth <= 768) {
      toggleSidebar();
    }
  };

  const handleNavClick = () => {
    // Close sidebar on mobile after navigation
    if (window.innerWidth <= 768) {
      toggleSidebar();
    }
  };

  return (
    <>
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">KM</div>
        <div>
          <div style={{ fontWeight: 600 }}>車輛維修知識庫</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            AI 智慧助理
          </div>
        </div>
      </div>

      {/* New Chat Button */}
      <div style={{ padding: '0.5rem' }}>
        <button
          onClick={handleNewChat}
          className="btn btn-primary"
          style={{ width: '100%', justifyContent: 'center' }}
        >
          <Add size={16} />
          新對話
        </button>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="nav-section">主選單</div>
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`nav-item ${pathname === item.href ? 'active' : ''}`}
            onClick={handleNavClick}
          >
            <item.icon size={20} />
            {item.label}
          </Link>
        ))}

        {/* Admin Section */}
        {user?.role === 'admin' && (
          <>
            <div className="nav-section">管理</div>
            {adminItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <item.icon size={20} />
                {item.label}
              </Link>
            ))}
          </>
        )}

        {/* Recent Conversations */}
        {conversations.length > 0 && (
          <>
            <div className="nav-section">最近對話</div>
            {conversations.slice(0, 5).map((conv) => (
              <div
                key={conv.id}
                className={`nav-item ${conv.id === activeConversationId ? 'active' : ''}`}
                onClick={() => {
                  setActiveConversation(conv.id);
                  router.push('/chat');
                  handleNavClick();
                }}
                style={{ fontSize: '0.875rem', cursor: 'pointer' }}
              >
                <Chat size={16} />
                <span style={{ 
                  overflow: 'hidden', 
                  textOverflow: 'ellipsis', 
                  whiteSpace: 'nowrap' 
                }}>
                  {conv.title}
                </span>
              </div>
            ))}
            {conversations.length > 5 && (
              <Link
                href="/history"
                className="nav-item"
                style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}
                onClick={handleNavClick}
              >
                查看全部 ({conversations.length})
              </Link>
            )}
          </>
        )}
      </nav>

      {/* User Info */}
      <div style={{ 
        padding: '1rem', 
        borderTop: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        marginTop: 'auto'
      }}>
        <div style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          background: 'var(--primary)',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '0.875rem',
          fontWeight: 500
        }}>
          {user?.name?.charAt(0) || 'U'}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>
            {user?.name || '訪客'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {user?.role === 'admin' ? '管理員' : user?.role === 'user' ? '使用者' : '訪客'}
          </div>
        </div>
        <button className="input-btn" title="登出" onClick={handleLogout}>
          <Logout size={18} />
        </button>
      </div>
    </>
  );
}
