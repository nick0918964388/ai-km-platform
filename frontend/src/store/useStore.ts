import { create } from 'zustand';
import { User, Conversation, Message, GlobalSettings } from '@/types';

// Helper functions for user-specific localStorage keys
const getConversationsKey = (userId: string) => `conversations_${userId}`;
const getActiveConversationKey = (userId: string) => `activeConversationId_${userId}`;

// Load conversations from localStorage for a specific user
const loadUserConversations = (userId: string | null): Conversation[] => {
  if (typeof window === 'undefined' || !userId) return [];
  try {
    const stored = localStorage.getItem(getConversationsKey(userId));
    if (stored) {
      const parsed = JSON.parse(stored);
      // Restore Date objects
      return parsed.map((conv: any) => ({
        ...conv,
        createdAt: new Date(conv.createdAt),
        updatedAt: new Date(conv.updatedAt),
        messages: conv.messages.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        })),
      }));
    }
  } catch (e) {
    console.error('Failed to load conversations:', e);
  }
  return [];
};

// Save conversations to localStorage for a specific user
const saveUserConversations = (userId: string | null, conversations: Conversation[]) => {
  if (typeof window === 'undefined' || !userId) return;
  try {
    localStorage.setItem(getConversationsKey(userId), JSON.stringify(conversations));
  } catch (e) {
    console.error('Failed to save conversations:', e);
  }
};

// Load active conversation ID from localStorage for a specific user
const loadActiveConversationId = (userId: string | null): string | null => {
  if (typeof window === 'undefined' || !userId) return null;
  return localStorage.getItem(getActiveConversationKey(userId));
};

// Save active conversation ID to localStorage for a specific user
const saveActiveConversationId = (userId: string | null, convId: string | null) => {
  if (typeof window === 'undefined' || !userId) return;
  if (convId) {
    localStorage.setItem(getActiveConversationKey(userId), convId);
  } else {
    localStorage.removeItem(getActiveConversationKey(userId));
  }
};

interface AppState {
  // User
  user: User | null;
  setUser: (user: User | null) => void;

  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;
  setActiveConversation: (id: string | null) => void;
  addConversation: (conversation: Conversation) => void;
  addMessage: (conversationId: string, message: Message) => void;
  updateMessage: (conversationId: string, messageId: string, content: string) => void;
  loadUserData: () => void;

  // UI
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebarCollapsed: () => void;

  // Settings
  settings: GlobalSettings;
  updateSettings: (settings: Partial<GlobalSettings>) => void;
}

const defaultSettings: GlobalSettings = {
  siteName: 'AI 知識管理平台',
  primaryColor: '#0f62fe',
  allowRegistration: false,
  defaultRole: 'user',
  aiModel: 'gpt-4',
  maxTokens: 4096,
};

export const useStore = create<AppState>((set, get) => ({
  // User
  user: null,
  setUser: (user) => {
    set({ user });
    // Load user-specific conversations when user changes
    if (user) {
      const conversations = loadUserConversations(user.id);
      const activeConversationId = loadActiveConversationId(user.id);
      set({ conversations, activeConversationId });
    } else {
      set({ conversations: [], activeConversationId: null });
    }
  },
  
  // Conversations - now user-specific
  conversations: [],
  activeConversationId: null,
  
  // Load user data from localStorage (called after hydration)
  // Always start with a fresh new conversation (activeConversationId = null)
  // Users can switch to old conversations from the sidebar
  loadUserData: () => {
    const { user } = get();
    if (user) {
      const conversations = loadUserConversations(user.id);
      // Don't restore activeConversationId - always start fresh
      set({ conversations, activeConversationId: null });
    }
  },
  
  setActiveConversation: (id) => {
    const { user } = get();
    saveActiveConversationId(user?.id || null, id);
    set({ activeConversationId: id });
  },
  
  addConversation: (conversation) =>
    set((state) => {
      const newConversations = [conversation, ...state.conversations];
      saveUserConversations(state.user?.id || null, newConversations);
      saveActiveConversationId(state.user?.id || null, conversation.id);
      return {
        conversations: newConversations,
        activeConversationId: conversation.id,
      };
    }),
    
  addMessage: (conversationId, message) =>
    set((state) => {
      const newConversations = state.conversations.map((conv) =>
        conv.id === conversationId
          ? { ...conv, messages: [...conv.messages, message], updatedAt: new Date() }
          : conv
      );
      saveUserConversations(state.user?.id || null, newConversations);
      return { conversations: newConversations };
    }),

  updateMessage: (conversationId: string, messageId: string, content: string) =>
    set((state) => {
      const newConversations = state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: conv.messages.map((msg) =>
                msg.id === messageId ? { ...msg, content } : msg
              ),
              updatedAt: new Date(),
            }
          : conv
      );
      saveUserConversations(state.user?.id || null, newConversations);
      return { conversations: newConversations };
    }),
  
  // UI
  sidebarOpen: false, // Start closed on mobile to avoid flash
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  sidebarCollapsed: typeof window !== 'undefined'
    ? localStorage.getItem('sidebarCollapsed') === 'true'
    : false,
  setSidebarCollapsed: (collapsed) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('sidebarCollapsed', String(collapsed));
    }
    set({ sidebarCollapsed: collapsed });
  },
  toggleSidebarCollapsed: () =>
    set((state) => {
      const newCollapsed = !state.sidebarCollapsed;
      if (typeof window !== 'undefined') {
        localStorage.setItem('sidebarCollapsed', String(newCollapsed));
      }
      return { sidebarCollapsed: newCollapsed };
    }),

  // Settings
  settings: defaultSettings,
  updateSettings: (newSettings) =>
    set((state) => ({
      settings: { ...state.settings, ...newSettings },
    })),
}));
