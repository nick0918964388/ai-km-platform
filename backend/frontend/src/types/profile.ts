/**
 * Profile-related TypeScript type definitions
 */

/**
 * User profile interface matching backend UserProfile model
 */
export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  account_level: 'free' | 'pro' | 'enterprise';
  created_at: string; // ISO 8601 format
  updated_at: string; // ISO 8601 format
}

/**
 * Profile update request payload
 */
export interface ProfileUpdateRequest {
  display_name: string;
}

/**
 * Avatar upload response
 */
export interface AvatarUploadResponse {
  avatar_url: string;
  message: string;
}

/**
 * Profile API error response
 */
export interface ProfileError {
  error: string;
  message: string;
  details?: Record<string, any>;
}
