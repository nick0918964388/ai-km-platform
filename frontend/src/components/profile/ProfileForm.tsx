'use client';

import { useState, useEffect } from 'react';
import {
  TextInput,
  Button,
  InlineNotification,
  Form,
  FormGroup,
  Stack,
} from '@carbon/react';
import { UserAvatar, Save } from '@carbon/icons-react';
import { useProfile } from '@/hooks/useProfile';
import AvatarUploader from './AvatarUploader';

export default function ProfileForm() {
  const {
    profile,
    profileLoading,
    profileError,
    fetchProfile,
    updateDisplayName,
  } = useProfile();

  const [displayName, setDisplayName] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Load profile on mount only once
  useEffect(() => {
    fetchProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Intentionally empty - only fetch on mount

  // Sync display name with profile
  useEffect(() => {
    if (profile) {
      setDisplayName(profile.display_name);
    }
  }, [profile]);

  // Clear success message after 5 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  /**
   * Validate display name
   * - Must be 2-50 characters
   * - Cannot be whitespace-only
   */
  const validateDisplayName = (value: string): string | null => {
    const trimmed = value.trim();

    if (trimmed.length === 0) {
      return 'Display name cannot be empty';
    }

    if (trimmed.length < 2) {
      return 'Display name must be at least 2 characters';
    }

    if (trimmed.length > 50) {
      return 'Display name cannot exceed 50 characters';
    }

    if (value !== trimmed) {
      return 'Display name cannot start or end with whitespace';
    }

    return null;
  };

  /**
   * Handle display name change with inline validation
   */
  const handleDisplayNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setDisplayName(value);
    setValidationError(validateDisplayName(value));
    setSuccessMessage(null);
  };

  /**
   * Handle form submission with optimistic updates
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Final validation
    const error = validateDisplayName(displayName);
    if (error) {
      setValidationError(error);
      return;
    }

    // Check if name actually changed
    if (profile && displayName === profile.display_name) {
      setSuccessMessage('No changes to save');
      return;
    }

    setIsSaving(true);
    setValidationError(null);
    setSuccessMessage(null);

    try {
      // Optimistic update happens inside the hook
      await updateDisplayName(displayName);
      setSuccessMessage('Profile updated successfully!');
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : 'Failed to update profile';
      setValidationError(errorMsg);
    } finally {
      setIsSaving(false);
    }
  };

  const isFormValid = !validationError && displayName.trim().length >= 2;
  const hasChanges = profile && displayName !== profile.display_name;

  if (profileLoading && !profile) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Loading profile...</p>
      </div>
    );
  }

  if (profileError && !profile) {
    return (
      <div className="p-6">
        <InlineNotification
          kind="error"
          title="Error"
          subtitle={profileError}
          hideCloseButton
        />
      </div>
    );
  }

  if (!profile) {
    return null;
  }

  return (
    <div className="max-w-2xl">
      <Form onSubmit={handleSubmit}>
        <Stack gap={6}>
          {/* Success notification */}
          {successMessage && (
            <InlineNotification
              kind="success"
              title="Success"
              subtitle={successMessage}
              onCloseButtonClick={() => setSuccessMessage(null)}
            />
          )}

          {/* Error notification */}
          {validationError && (
            <InlineNotification
              kind="error"
              title="Validation Error"
              subtitle={validationError}
              hideCloseButton
            />
          )}

          {/* Avatar Uploader */}
          <div className="mb-6">
            <AvatarUploader />
          </div>

          <FormGroup legendText="">
            {/* Display Name - Editable */}
            <TextInput
              id="display-name"
              labelText="Display Name"
              placeholder="Enter your display name"
              value={displayName}
              onChange={handleDisplayNameChange}
              invalid={!!validationError}
              invalidText={validationError || ''}
              disabled={isSaving}
              helperText="2-50 characters"
            />

            {/* Email - Read-only */}
            <div className="mt-4">
              <TextInput
                id="email"
                labelText="Email"
                value={profile.email}
                readOnly
                disabled
                helperText="Email cannot be changed"
              />
            </div>

            {/* Account Level - Read-only */}
            <div className="mt-4">
              <TextInput
                id="account-level"
                labelText="Account Level"
                value={
                  profile.account_level === 'free'
                    ? 'Free'
                    : profile.account_level === 'pro'
                    ? 'Pro'
                    : 'Enterprise'
                }
                readOnly
                disabled
                helperText="Contact support to upgrade your account"
              />
            </div>

            {/* Created At - Read-only */}
            <div className="mt-4">
              <TextInput
                id="created-at"
                labelText="Account Created"
                value={new Date(profile.created_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
                readOnly
                disabled
              />
            </div>
          </FormGroup>

          {/* Save Button */}
          <div className="flex items-center gap-4 mt-6">
            <Button
              type="submit"
              kind="primary"
              renderIcon={Save}
              disabled={!isFormValid || !hasChanges || isSaving}
            >
              {isSaving ? 'Saving...' : 'Save Changes'}
            </Button>

            {hasChanges && !isSaving && (
              <span className="text-sm text-gray-500">You have unsaved changes</span>
            )}
          </div>
        </Stack>
      </Form>
    </div>
  );
}
