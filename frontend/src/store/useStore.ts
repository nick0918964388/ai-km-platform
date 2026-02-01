import { create } from 'zustand';
import { User, Conversation, Message, GlobalSettings } from '@/types';

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
  
  // UI
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  
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

export const useStore = create<AppState>((set) => ({
  // User
  user: null,
  setUser: (user) => set({ user }),
  
  // Conversations
  conversations: [],
  activeConversationId: null,
  setActiveConversation: (id) => set({ activeConversationId: id }),
  addConversation: (conversation) =>
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: conversation.id,
    })),
  addMessage: (conversationId, message) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? { ...conv, messages: [...conv.messages, message], updatedAt: new Date() }
          : conv
      ),
    })),
  
  // UI
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  
  // Settings
  settings: defaultSettings,
  updateSettings: (newSettings) =>
    set((state) => ({
      settings: { ...state.settings, ...newSettings },
    })),
}));
