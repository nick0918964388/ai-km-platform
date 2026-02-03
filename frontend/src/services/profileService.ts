/**
 * Profile Service
 * Handles user profile management API calls
 */

import { UserProfile, ProfileUpdateRequest, AvatarUploadResponse } from '@/types/profile';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

/**
 * Get the current user's profile
 * @returns UserProfile object
 * @throws Error if request fails
 */
export async function getProfile(): Promise<UserProfile> {
  try {
    const response = await fetch(`${API_URL}/api/profile`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to fetch profile: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Profile fetch error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to fetch profile'
    );
  }
}

/**
 * Update the current user's profile display name
 * @param displayName - New display name (2-50 characters)
 * @returns Updated UserProfile object
 * @throws Error if request fails or validation fails
 */
export async function updateProfile(displayName: string): Promise<UserProfile> {
  try {
    const requestData: ProfileUpdateRequest = { display_name: displayName };

    const response = await fetch(`${API_URL}/api/profile`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to update profile: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Profile update error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to update profile'
    );
  }
}

/**
 * Upload a new avatar image for the current user
 * @param file - Image file (JPG, PNG, or GIF, max 5MB)
 * @returns AvatarUploadResponse with new avatar URL
 * @throws Error if upload fails or validation fails
 */
export async function uploadAvatar(file: File): Promise<AvatarUploadResponse> {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_URL}/api/profile/avatar`, {
      method: 'POST',
      headers: {
        ...(API_KEY && { 'X-API-Key': API_KEY }),
        // Don't set Content-Type - browser will set it with boundary for multipart
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to upload avatar: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Avatar upload error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to upload avatar'
    );
  }
}

/**
 * Remove the current user's avatar and revert to initials
 * @returns Success message
 * @throws Error if request fails
 */
export async function deleteAvatar(): Promise<{ message: string }> {
  try {
    const response = await fetch(`${API_URL}/api/profile/avatar`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to delete avatar: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Avatar delete error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to delete avatar'
    );
  }
}
