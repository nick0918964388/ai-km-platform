import { create } from 'zustand';
import { User, Conversation, Message, GlobalSettings } from '@/types';
import { UserProfile } from '@/types/profile';
import { DashboardMetrics } from '@/types/dashboard';

// Helper functions for user-specific localStorage keys
const getConversationsKey = (userId: string) => `conversations_${userId}`;
const getActiveConversationKey = (userId: string) => `activeConversationId_${userId}`;

// User localStorage helpers
const USER_STORAGE_KEY = 'user_session';
const loadStoredUser = (): User | null => {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(USER_STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
};

const saveStoredUser = (user: User | null) => {
  if (typeof window === 'undefined') return;
  if (user) {
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_STORAGE_KEY);
  }
};

// Profile localStorage helpers
const PROFILE_STORAGE_KEY = 'user_profile';
const loadStoredProfile = (): UserProfile | null => {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(PROFILE_STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
};

const saveStoredProfile = (profile: UserProfile | null) => {
  if (typeof window === 'undefined') return;
  if (profile) {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
  } else {
    localStorage.removeItem(PROFILE_STORAGE_KEY);
  }
};

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

  // Profile
  profile: UserProfile | null;
  profileLoading: boolean;
  profileError: string | null;
  setProfile: (profile: UserProfile) => void;
  updateProfile: (updates: Partial<UserProfile>) => void;
  clearProfile: () => void;

  // Dashboard
  dashboardMetrics: DashboardMetrics | null;
  dashboardLoading: boolean;
  dashboardError: string | null;
  setDashboardMetrics: (metrics: DashboardMetrics) => void;
  clearDashboard: () => void;

  // Avatar upload
  avatarUploading: boolean;
  avatarUploadProgress: number;
  setAvatarUploading: (uploading: boolean, progress?: number) => void;

  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;
  setActiveConversation: (id: string | null) => void;
  addConversation: (conversation: Conversation) => void;
  deleteConversation: (conversationId: string) => void;
  updateConversationTitle: (conversationId: string, title: string) => void;
  addMessage: (conversationId: string, message: Message) => void;
  updateMessage: (conversationId: string, messageId: string, content: string, extra?: { sources?: any[]; query?: string; sqlResult?: any; clarification?: any; jobId?: string }) => void;
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
  user: loadStoredUser(),
  setUser: (user) => {
    saveStoredUser(user);
    set({ user });
    if (user) {
      import('@/lib/api').then(({ apiListConversations, apiGetConversation }) => {
        apiListConversations().then(async (serverConvs) => {
          if (!serverConvs?.length) {
            set({ conversations: loadUserConversations(user.id) });
            return;
          }
          const fullConvs = await Promise.all(
            serverConvs.slice(0, 30).map(async (c: any) => {
              try {
                const full = await apiGetConversation(c.id);
                return {
                  id: full.id,
                  title: full.title,
                  createdAt: new Date(full.createdAt),
                  updatedAt: new Date(full.updatedAt),
                  messages: (full.messages || []).map((m: any) => ({
                    ...m,
                    timestamp: new Date(m.timestamp || m.created_at),
                  })),
                };
              } catch {
                return null;
              }
            })
          );
          const valid = fullConvs.filter(Boolean) as Conversation[];
          set({ conversations: valid });
          saveUserConversations(user.id, valid);
        }).catch(() => {
          set({ conversations: loadUserConversations(user.id) });
        });
      });
      const storedActiveId = loadActiveConversationId(user.id);
      set({ activeConversationId: storedActiveId || null });
    } else {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token');
      }
      set({ conversations: [], activeConversationId: null });
    }
  },

  // Profile state
  profile: loadStoredProfile(),
  profileLoading: false,
  profileError: null,

  setProfile: (profile) => {
    saveStoredProfile(profile);
    set({ profile, profileError: null });
  },

  updateProfile: (updates) => {
    const currentProfile = get().profile;
    if (!currentProfile) return;

    const updatedProfile = { ...currentProfile, ...updates };
    saveStoredProfile(updatedProfile);
    set({ profile: updatedProfile });
  },

  clearProfile: () => {
    saveStoredProfile(null);
    set({ profile: null, dashboardMetrics: null });
  },

  // Dashboard state
  dashboardMetrics: null,
  dashboardLoading: false,
  dashboardError: null,

  setDashboardMetrics: (metrics) => {
    set({ dashboardMetrics: metrics, dashboardError: null });
  },

  clearDashboard: () => {
    set({ dashboardMetrics: null, dashboardError: null });
  },

  // Avatar upload state
  avatarUploading: false,
  avatarUploadProgress: 0,

  setAvatarUploading: (uploading, progress = 0) => {
    set({ avatarUploading: uploading, avatarUploadProgress: progress });
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
      // Load from localStorage immediately, then sync from server
      const conversations = loadUserConversations(user.id);
      set({ conversations, activeConversationId: null });
      import('@/lib/api').then(({ apiListConversations, apiGetConversation }) => {
        apiListConversations().then(async (serverConvs) => {
          if (!serverConvs?.length) return;
          const fullConvs = await Promise.all(
            serverConvs.slice(0, 30).map(async (c: any) => {
              try {
                const full = await apiGetConversation(c.id);
                return {
                  id: full.id,
                  title: full.title,
                  createdAt: new Date(full.createdAt),
                  updatedAt: new Date(full.updatedAt),
                  messages: (full.messages || []).map((m: any) => ({
                    ...m,
                    timestamp: new Date(m.timestamp || m.created_at),
                  })),
                };
              } catch {
                return null;
              }
            })
          );
          const valid = fullConvs.filter(Boolean) as Conversation[];
          set({ conversations: valid });
          saveUserConversations(user.id, valid);
        }).catch(console.error);
      });
    }
  },
  
  setActiveConversation: (id) => {
    const { user } = get();
    saveActiveConversationId(user?.id || null, id);
    set({ activeConversationId: id });
  },
  
  addConversation: (conversation) => {
    const state = get();
    const updated = [conversation, ...state.conversations];
    set({ conversations: updated, activeConversationId: conversation.id });
    import('@/lib/api').then(({ apiCreateConversation }) => {
      apiCreateConversation(conversation.id, conversation.title).catch(console.error);
    });
    if (state.user?.id) {
      saveUserConversations(state.user.id, updated);
      saveActiveConversationId(state.user.id, conversation.id);
    }
  },

  deleteConversation: (conversationId) => {
    const state = get();
    const updated = state.conversations.filter(c => c.id !== conversationId);
    const newActive = state.activeConversationId === conversationId
      ? (updated[0]?.id || null)
      : state.activeConversationId;
    set({ conversations: updated, activeConversationId: newActive });
    import('@/lib/api').then(({ apiDeleteConversation }) => {
      apiDeleteConversation(conversationId).catch(console.error);
    });
    if (state.user?.id) {
      saveUserConversations(state.user.id, updated);
      if (newActive !== state.activeConversationId) {
        saveActiveConversationId(state.user.id, newActive);
      }
    }
  },

  updateConversationTitle: (conversationId, title) => {
    const state = get();
    const updated = state.conversations.map(c =>
      c.id === conversationId ? { ...c, title, updatedAt: new Date() } : c
    );
    set({ conversations: updated });
    import('@/lib/api').then(({ apiUpdateConversationTitle }) => {
      apiUpdateConversationTitle(conversationId, title).catch(console.error);
    });
    if (state.user?.id) saveUserConversations(state.user.id, updated);
  },
    
  addMessage: (conversationId, message) => {
    const state = get();
    const updated = state.conversations.map(c =>
      c.id === conversationId
        ? { ...c, messages: [...c.messages, message], updatedAt: new Date() }
        : c
    );
    set({ conversations: updated });
    import('@/lib/api').then(({ apiAddMessage }) => {
      const { sources, sqlResult, clarification, query, jobId, ...rest } = message as any;
      const metadata = { sources, sqlResult, clarification, query, jobId };
      apiAddMessage(conversationId, {
        id: message.id,
        role: message.role,
        content: message.content,
        metadata: Object.fromEntries(Object.entries(metadata).filter(([_, v]) => v !== undefined)),
      }).catch(console.error);
    });
    if (state.user?.id) saveUserConversations(state.user.id, updated);
  },

  updateMessage: (conversationId: string, messageId: string, content: string, extra?: { sources?: any[]; query?: string; sqlResult?: any; clarification?: any; jobId?: string }) => {
    const state = get();
    const updated = state.conversations.map(c => {
      if (c.id !== conversationId) return c;
      return {
        ...c,
        updatedAt: new Date(),
        messages: c.messages.map(m => {
          if (m.id !== messageId) return m;
          return {
            ...m,
            content,
            ...(extra?.sources !== undefined && { sources: extra.sources }),
            ...(extra?.query !== undefined && { query: extra.query }),
            ...(extra?.sqlResult !== undefined && { sqlResult: extra.sqlResult }),
            ...(extra?.clarification !== undefined && { clarification: extra.clarification }),
            ...(extra?.jobId !== undefined && { jobId: extra.jobId }),
          };
        }),
      };
    });
    set({ conversations: updated });
    if (extra?.sources || extra?.sqlResult || extra?.query || extra?.clarification) {
      import('@/lib/api').then(({ apiAddMessage }) => {
        const msg = updated.find(c => c.id === conversationId)?.messages.find(m => m.id === messageId);
        if (msg) {
          const { sources, sqlResult, clarification, query, jobId, ...rest } = msg as any;
          const metadata = { sources, sqlResult, clarification, query, jobId };
          apiAddMessage(conversationId, {
            id: messageId,
            role: msg.role,
            content: msg.content,
            metadata: Object.fromEntries(Object.entries(metadata).filter(([_, v]) => v !== undefined)),
          }).catch(console.error);
        }
      });
    }
    if (state.user?.id) saveUserConversations(state.user.id, updated);
  },
  
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
