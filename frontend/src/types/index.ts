export type UserRole = 'admin' | 'analyst' | 'user' | 'guest';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
  createdAt: Date;
  lastLogin?: Date;
}

export interface ClarificationData {
  message: string;
  options: { label: string; query: string }[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  attachments?: Attachment[];
  sources?: SearchResult[];
  query?: string; // Store original query for highlighting
  sqlResult?: any; // NL→SQL structured result (persisted for history reload)
  clarification?: ClarificationData; // Agentic RAG clarification options
  jobId?: string; // For async job recovery
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
