'use client';

import { useState, useCallback, useRef } from 'react';
import { useStore } from '@/store/useStore';
import { uploadAvatar, deleteAvatar } from '@/services/profileService';

// File validation constants
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif'];

export interface AvatarUploadState {
  /** Currently selected file */
  file: File | null;
  /** Preview URL for the selected file */
  previewUrl: string | null;
  /** Upload in progress */
  uploading: boolean;
  /** Upload progress (0-100) */
  uploadProgress: number;
  /** Error message if upload failed */
  error: string | null;
  /** Success message after upload */
  success: string | null;
}

export interface UseAvatarUploadReturn extends AvatarUploadState {
  /** Select a file and generate preview */
  selectFile: (file: File) => Promise<boolean>;
  /** Upload the selected file */
  uploadFile: () => Promise<boolean>;
  /** Remove current avatar */
  removeAvatar: () => Promise<boolean>;
  /** Clear selection and preview */
  clearSelection: () => void;
  /** Clear error message */
  clearError: () => void;
  /** Validate file without selecting it */
  validateFile: (file: File) => { valid: boolean; error?: string };
}

/**
 * Hook for managing avatar upload state and operations
 */
export function useAvatarUpload(): UseAvatarUploadReturn {
  const [state, setState] = useState<AvatarUploadState>({
    file: null,
    previewUrl: null,
    uploading: false,
    uploadProgress: 0,
    error: null,
    success: null,
  });

  const previewUrlRef = useRef<string | null>(null);
  const profile = useStore((state) => state.profile);
  const updateProfile = useStore((state) => state.updateProfile);
  const setAvatarUploading = useStore((state) => state.setAvatarUploading);

  /**
   * Validate file type and size
   */
  const validateFile = useCallback(
    (file: File): { valid: boolean; error?: string } => {
      // Check file type
      if (!ALLOWED_TYPES.includes(file.type)) {
        return {
          valid: false,
          error: `Invalid file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`,
        };
      }

      // Check file extension as additional validation
      const fileName = file.name.toLowerCase();
      const hasValidExtension = ALLOWED_EXTENSIONS.some((ext) =>
        fileName.endsWith(ext)
      );

      if (!hasValidExtension) {
        return {
          valid: false,
          error: `Invalid file extension. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`,
        };
      }

      // Check file size
      if (file.size > MAX_FILE_SIZE) {
        const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
        return {
          valid: false,
          error: `File size (${sizeMB}MB) exceeds maximum allowed size of 5MB`,
        };
      }

      return { valid: true };
    },
    []
  );

  /**
   * Select a file and generate preview
   */
  const selectFile = useCallback(
    async (file: File): Promise<boolean> => {
      // Validate file
      const validation = validateFile(file);
      if (!validation.valid) {
        setState((prev) => ({
          ...prev,
          error: validation.error || 'Invalid file',
          success: null,
        }));
        return false;
      }

      // Revoke previous preview URL to free memory
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }

      // Generate preview URL
      const previewUrl = URL.createObjectURL(file);
      previewUrlRef.current = previewUrl;

      setState((prev) => ({
        ...prev,
        file,
        previewUrl,
        error: null,
        success: null,
      }));

      return true;
    },
    [validateFile]
  );

  /**
   * Upload the selected file
   */
  const uploadFile = useCallback(async (): Promise<boolean> => {
    if (!state.file) {
      setState((prev) => ({ ...prev, error: 'No file selected' }));
      return false;
    }

    setState((prev) => ({
      ...prev,
      uploading: true,
      uploadProgress: 0,
      error: null,
      success: null,
    }));
    setAvatarUploading(true, 0);

    // Simulate progress for better UX
    const progressInterval = setInterval(() => {
      setState((prev) => {
        const newProgress = Math.min(prev.uploadProgress + 10, 90);
        setAvatarUploading(true, newProgress);
        return { ...prev, uploadProgress: newProgress };
      });
    }, 200);

    try {
      // Upload avatar
      const response = await uploadAvatar(state.file);

      // Update profile in store
      if (profile) {
        updateProfile({ avatar_url: response.avatar_url });
      }

      // Clear selection and show success
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }

      setState({
        file: null,
        previewUrl: null,
        uploading: false,
        uploadProgress: 100,
        error: null,
        success: 'Avatar uploaded successfully!',
      });
      setAvatarUploading(false, 100);

      return true;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to upload avatar';

      setState((prev) => ({
        ...prev,
        uploading: false,
        uploadProgress: 0,
        error: errorMessage,
        success: null,
      }));
      setAvatarUploading(false, 0);

      return false;
    } finally {
      // Always clear interval to prevent memory leak
      clearInterval(progressInterval);
    }
  }, [state.file, profile, updateProfile, setAvatarUploading]);

  /**
   * Remove current avatar
   */
  const removeAvatar = useCallback(async (): Promise<boolean> => {
    setState((prev) => ({
      ...prev,
      uploading: true,
      error: null,
      success: null,
    }));

    try {
      await deleteAvatar();

      // Update profile in store
      if (profile) {
        updateProfile({ avatar_url: null });
      }

      setState((prev) => ({
        ...prev,
        uploading: false,
        success: 'Avatar removed successfully',
      }));

      return true;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to remove avatar';

      setState((prev) => ({
        ...prev,
        uploading: false,
        error: errorMessage,
      }));

      return false;
    }
  }, [profile, updateProfile]);

  /**
   * Clear file selection and preview
   */
  const clearSelection = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }

    setState((prev) => ({
      ...prev,
      file: null,
      previewUrl: null,
      error: null,
      success: null,
    }));
  }, []);

  /**
   * Clear error message
   */
  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    selectFile,
    uploadFile,
    removeAvatar,
    clearSelection,
    clearError,
    validateFile,
  };
}
