/**
 * Profile Types
 * Type definitions for user profile management
 */

export interface UserProfile {
  id: string;
  username: string;
  display_name: string;
  email?: string;
  avatar_url?: string | null;
  role: string;
  created_at?: string;
  updated_at?: string;
  /** Optional additional fields */
  [key: string]: unknown;
}

export interface ProfileUpdateRequest {
  display_name: string;
}

export interface AvatarUploadResponse {
  avatar_url: string;
  message?: string;
}
