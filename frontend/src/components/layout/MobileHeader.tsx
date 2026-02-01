'use client';

import { Menu, Close, Add } from '@carbon/icons-react';
import { useStore } from '@/store/useStore';

export default function MobileHeader() {
  const { sidebarOpen, toggleSidebar, addConversation } = useStore();

  const handleNewChat = () => {
    const newConv = {
      id: Date.now().toString(),
      title: '新對話',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    addConversation(newConv);
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
      
      <button 
        className="mobile-menu-btn"
        onClick={handleNewChat}
        aria-label="New chat"
      >
        <Add size={24} />
      </button>
    </div>
  );
}
