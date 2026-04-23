/**
 * Profile Service
 * Handles user profile management API calls
 */

import { UserProfile, ProfileUpdateRequest, AvatarUploadResponse } from '@/types/profile';
import { apiGet, apiRequest, apiDelete, apiUpload } from '@/lib/api';

/**
 * Get the current user's profile
 * @returns UserProfile object
 * @throws Error if request fails
 */
export async function getProfile(): Promise<UserProfile> {
  return apiGet<UserProfile>('/api/profile');
}

/**
 * Update the current user's profile display name
 * @param displayName - New display name (2-50 characters)
 * @returns Updated UserProfile object
 * @throws Error if request fails or validation fails
 */
export async function updateProfile(displayName: string): Promise<UserProfile> {
  const requestData: ProfileUpdateRequest = { display_name: displayName };
  return apiRequest<UserProfile>('/api/profile', {
    method: 'PATCH',
    body: JSON.stringify(requestData),
  });
}

/**
 * Upload a new avatar image for the current user
 * @param file - Image file (JPG, PNG, or GIF, max 5MB)
 * @returns AvatarUploadResponse with new avatar URL
 * @throws Error if upload fails or validation fails
 */
export async function uploadAvatar(file: File): Promise<AvatarUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  // apiUpload handles auth header and multipart (no Content-Type override)
  return apiUpload<AvatarUploadResponse>('/api/profile/avatar', formData);
}

/**
 * Remove the current user's avatar and revert to initials
 * @returns Success message
 * @throws Error if request fails
 */
export async function deleteAvatar(): Promise<{ message: string }> {
  return apiDelete<{ message: string }>('/api/profile/avatar');
}
