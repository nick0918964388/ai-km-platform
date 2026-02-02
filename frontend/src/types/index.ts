export type UserRole = 'admin' | 'user' | 'guest';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
  createdAt: Date;
  lastLogin?: Date;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  attachments?: Attachment[];
}

export interface Attachment {
  id: string;
  type: 'image' | 'audio' | 'file';
  url: string;
  name: string;
  size?: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface GlobalSettings {
  siteName: string;
  logo?: string;
  primaryColor: string;
  allowRegistration: boolean;
  defaultRole: UserRole;
  aiModel: string;
  maxTokens: number;
}

export interface SearchResult {
  id: string;
  content: string;
  doc_type: 'text' | 'image';
  document_id: string;
  document_name: string;
  score: number;
  image_base64?: string;
  file_url?: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface MessageMetadata {
  model: string;
  duration_ms: number;
  tokens: TokenUsage | null;
}
