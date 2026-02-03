'use client';

import { useEffect, useState } from 'react';
import {
  FileUploader,
  Button,
  InlineNotification,
  Modal,
} from '@carbon/react';
import { TrashCan, CheckmarkFilled } from '@carbon/icons-react';
import { useProfile } from '@/hooks/useProfile';
import { useAvatarUpload } from '@/hooks/useAvatarUpload';
import AccountInitials from './AccountInitials';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function AvatarUploader() {
  const { profile } = useProfile();
  const {
    file,
    previewUrl,
    uploading,
    uploadProgress,
    error,
    success,
    selectFile,
    uploadFile,
    removeAvatar,
    clearSelection,
    clearError,
  } = useAvatarUpload();

  const [showRemoveModal, setShowRemoveModal] = useState(false);
  const [removing, setRemoving] = useState(false);

  // Clear success message after 5 seconds
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => clearSelection(), 5000);
      return () => clearTimeout(timer);
    }
  }, [success, clearSelection]);

  /**
   * Handle file selection from FileUploader
   */
  const handleFileChange = async (event: any) => {
    const addedFiles = event.target.files || event.addedFiles;

    if (addedFiles && addedFiles.length > 0) {
      const selectedFile = addedFiles[0];
      await selectFile(selectedFile);
    }
  };

  /**
   * Handle avatar upload
   */
  const handleUpload = async () => {
    const success = await uploadFile();
    if (success) {
      clearSelection();
    }
  };

  /**
   * Handle avatar removal with confirmation
   */
  const handleRemoveConfirm = async () => {
    setRemoving(true);
    const success = await removeAvatar();
    setRemoving(false);
    setShowRemoveModal(false);

    if (success) {
      clearSelection();
    }
  };

  if (!profile) {
    return null;
  }

  // Get current avatar URL (from profile or preview)
  const currentAvatarUrl = previewUrl || profile.avatar_url;
  const hasAvatar = !!currentAvatarUrl;

  return (
    <div className="space-y-4">
      {/* Avatar Preview */}
      <div className="flex items-start gap-6">
        <div className="flex-shrink-0">
          {hasAvatar ? (
            <img
              src={
                previewUrl
                  ? previewUrl
                  : `${API_URL}${profile.avatar_url}`
              }
              alt={`Avatar for ${profile.display_name}`}
              className="w-32 h-32 rounded-full object-cover border-2 border-gray-200"
            />
          ) : (
            <AccountInitials displayName={profile.display_name} size={128} />
          )}
        </div>

        <div className="flex-1">
          <h3 className="text-lg font-medium mb-2">Profile Picture</h3>
          <p className="text-sm text-gray-600 mb-4">
            {hasAvatar
              ? 'Your current profile picture'
              : 'No profile picture set. Upload an image or use your initials.'}
          </p>

          {/* File Upload */}
          {!previewUrl && (
            <FileUploader
              accept={['.jpg', '.jpeg', '.png', '.gif']}
              buttonLabel="Choose file"
              filenameStatus="edit"
              iconDescription="Clear file"
              labelDescription="Max file size: 5MB. Supported: JPG, PNG, GIF"
              labelTitle="Upload Avatar"
              onChange={handleFileChange}
              disabled={uploading}
            />
          )}

          {/* Preview Actions */}
          {previewUrl && file && (
            <div className="space-y-3">
              <div className="p-3 bg-blue-50 rounded border border-blue-200">
                <p className="text-sm font-medium text-blue-900">
                  Ready to upload: {file.name}
                </p>
                <p className="text-xs text-blue-700 mt-1">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>

              <div className="flex gap-3">
                <Button
                  kind="primary"
                  size="sm"
                  onClick={handleUpload}
                  disabled={uploading}
                >
                  {uploading
                    ? `Uploading... ${uploadProgress}%`
                    : 'Upload Avatar'}
                </Button>
                <Button
                  kind="secondary"
                  size="sm"
                  onClick={clearSelection}
                  disabled={uploading}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {/* Remove Avatar Button */}
          {!previewUrl && profile.avatar_url && (
            <div className="mt-4">
              <Button
                kind="danger--tertiary"
                size="sm"
                renderIcon={TrashCan}
                onClick={() => setShowRemoveModal(true)}
                disabled={uploading}
              >
                Remove Avatar
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Success Notification */}
      {success && (
        <InlineNotification
          kind="success"
          title="Success"
          subtitle={success}
          onCloseButtonClick={clearSelection}
        />
      )}

      {/* Error Notification */}
      {error && (
        <InlineNotification
          kind="error"
          title="Error"
          subtitle={error}
          onCloseButtonClick={clearError}
        />
      )}

      {/* Remove Confirmation Modal */}
      <Modal
        open={showRemoveModal}
        onRequestClose={() => setShowRemoveModal(false)}
        modalHeading="Remove Avatar"
        primaryButtonText="Remove"
        secondaryButtonText="Cancel"
        onRequestSubmit={handleRemoveConfirm}
        danger
        primaryButtonDisabled={removing}
      >
        <p>
          Are you sure you want to remove your profile picture? Your account
          initials will be displayed instead.
        </p>
      </Modal>
    </div>
  );
}
