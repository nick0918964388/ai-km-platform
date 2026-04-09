'use client';

import { usePathname } from 'next/navigation';
import {
  Chat,
  Settings,
  Logout,
  Dashboard,
  RecentlyViewed,
  Locked,
  DataBase,
  ChevronLeft,
  ChevronRight,
  Bot,
  User,
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import AccountInitials from '@/components/profile/AccountInitials';

const navItems = [
  { href: '/chat', label: 'AI 問答', icon: Chat },
  { href: '/history', label: '查詢紀錄', icon: RecentlyViewed },
  { href: '/admin/dashboard', label: '管理儀表板', icon: Dashboard, adminOnly: true },
  { href: '/admin/knowledge-base', label: '知識庫管理', icon: DataBase, adminOnly: true },
];

const settingsItems = [
  { href: '/admin/permissions', label: '權限設定', icon: Locked },
  { href: '/settings', label: '系統設定', icon: Settings },
  { href: '/profile', label: '個人資料', icon: User },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, setUser, profile, sidebarOpen, toggleSidebar, sidebarCollapsed, toggleSidebarCollapsed } = useStore();

  const handleLogout = () => {
    setUser(null);
    window.location.href = '/login';
  };

  const handleNavClick = () => {
    // Close sidebar on mobile after navigation starts
    if (window.innerWidth <= 768) {
      // Use setTimeout to ensure navigation starts before closing sidebar
      setTimeout(() => {
        toggleSidebar();
      }, 50);
    }
  };

  return (
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''} ${sidebarCollapsed ? 'collapsed' : ''}`}>
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Bot size={22} />
        </div>
        {!sidebarCollapsed && (
          <div>
            <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              台鐵問答 AI
            </div>
            <div style={{ fontSize: '0.625rem', color: 'var(--accent)' }}>
              車輛維修知識庫
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {!sidebarCollapsed && <div className="nav-section">主選單</div>}
        {navItems
          .filter((item) => !item.adminOnly || user?.role === 'admin')
          .map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`nav-item ${pathname === item.href || pathname.startsWith(item.href + '/') ? 'active' : ''} ${sidebarCollapsed ? 'collapsed' : ''}`}
              onClick={handleNavClick}
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon size={20} />
              {!sidebarCollapsed && item.label}
            </a>
          ))}

        {/* Settings Section */}
        {user?.role === 'admin' && (
          <>
            {!sidebarCollapsed && <div className="nav-section">設定</div>}
            {settingsItems.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? 'active' : ''} ${sidebarCollapsed ? 'collapsed' : ''}`}
                onClick={handleNavClick}
                title={sidebarCollapsed ? item.label : undefined}
              >
                <item.icon size={20} />
                {!sidebarCollapsed && item.label}
              </a>
            ))}
          </>
        )}

      </nav>

      {/* Collapse Toggle Button */}
      <button
        onClick={toggleSidebarCollapsed}
        className="sidebar-collapse-btn-edge"
        title={sidebarCollapsed ? '展開側邊欄' : '收合側邊欄'}
      >
        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>

      {/* User Info */}
      <div className={`sidebar-user ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* Avatar - use profile avatar_url or AccountInitials */}
        {profile?.avatar_url ? (
          <img
            src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${profile.avatar_url}`}
            alt={profile.display_name}
            className="sidebar-user-avatar"
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              objectFit: 'cover',
            }}
          />
        ) : (
          <div style={{ width: '36px', height: '36px' }}>
            <AccountInitials
              displayName={profile?.display_name || user?.name || 'User'}
              size={36}
            />
          </div>
        )}
        {!sidebarCollapsed && (
          <>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">
                {profile?.display_name || user?.name || '訪客'}
              </div>
              <div className="sidebar-user-role">
                {user?.role === 'admin' ? '系統管理員' : user?.role === 'user' ? '使用者' : '訪客'}
              </div>
            </div>
            <button
              className="input-btn"
              title="登出"
              onClick={handleLogout}
              style={{ color: 'var(--text-muted)' }}
            >
              <Logout size={18} />
            </button>
          </>
        )}
      </div>
    </aside>
  );
}
