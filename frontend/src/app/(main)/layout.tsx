'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import MobileHeader from '@/components/layout/MobileHeader';
import { useStore } from '@/store/useStore';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, sidebarOpen, toggleSidebar, sidebarCollapsed, loadUserData } = useStore();
  const [isHydrated, setIsHydrated] = useState(false);

  // Wait for hydration to complete
  useEffect(() => {
    setIsHydrated(true);
  }, []);

  // Auth guard: redirect to login if not authenticated
  useEffect(() => {
    if (isHydrated && !user) {
      router.replace('/login');
    }
  }, [isHydrated, user, router]);

  // Load user-specific data on mount (after hydration)
  useEffect(() => {
    if (user) {
      loadUserData();
    }
  }, [user, loadUserData]);

  // Show loading state while checking auth
  if (!isHydrated || !user) {
    return (
      <div style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-secondary)'
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
        <main className="main-content">
          {children}
        </main>
      </div>
    </>
  );
}
