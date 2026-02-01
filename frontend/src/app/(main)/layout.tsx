'use client';

import Sidebar from '@/components/layout/Sidebar';
import MobileHeader from '@/components/layout/MobileHeader';
import { useStore } from '@/store/useStore';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { sidebarOpen, toggleSidebar } = useStore();

  return (
    <>
      {/* Mobile Header */}
      <MobileHeader />
      
      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div 
          className="sidebar-overlay"
          onClick={toggleSidebar}
        />
      )}
      
      <div className="app-container">
        <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
          <Sidebar />
        </aside>
        <main className="main-content">
          {children}
        </main>
      </div>
    </>
  );
}
