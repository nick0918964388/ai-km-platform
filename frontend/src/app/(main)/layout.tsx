'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import MobileHeader from '@/components/layout/MobileHeader';
import { useStore } from '@/store/useStore';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, sidebarOpen, toggleSidebar, sidebarCollapsed, loadUserData } = useStore();
  const [isHydrated, setIsHydrated] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false);

  // Wait for hydration to complete
  useEffect(() => {
    setIsHydrated(true);
  }, []);

  // Auth guard: redirect to login if not authenticated
  useEffect(() => {
    if (isHydrated && !user && !isRedirecting) {
      setIsRedirecting(true);
      router.push('/login');
    }
  }, [isHydrated, user, router, isRedirecting]);

  // Load user-specific data on mount (after hydration)
  useEffect(() => {
    if (user) {
      loadUserData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]); // Only re-run when user changes, not when loadUserData ref changes

  // Show loading screen only during initial hydration or when redirecting to login
  // Don't show it during normal navigation between pages
  if (!isHydrated) {
    return (
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-secondary)',
        zIndex: 9999,
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: 64,
            height: 64,
            background: 'var(--primary)',
            borderRadius: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontSize: '1.5rem',
            fontWeight: 700,
            margin: '0 auto 1rem',
            animation: 'pulse 1.5s infinite'
          }}>
            KM
          </div>
          <p style={{ color: 'var(--text-secondary)' }}>載入中...</p>
        </div>
      </div>
    );
  }

  // If not authenticated after hydration, don't render anything (will redirect)
  if (!user) {
    return null;
  }

  return (
    <>
      {/* Mobile Header */}
      <MobileHeader />

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className={`sidebar-overlay ${sidebarOpen ? 'visible' : ''}`}
          onClick={toggleSidebar}
          aria-hidden="true"
        />
      )}

      <div className="app-container">
        <Sidebar />
        <main key={pathname} className="main-content">
          {children}
        </main>
      </div>
    </>
  );
}
