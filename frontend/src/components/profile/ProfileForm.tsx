'use client';

import { useState, useEffect } from 'react';
import {
  Button,
  InlineNotification,
} from '@carbon/react';
import { Save } from '@carbon/icons-react';
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
    const isNotFound = profileError.includes('not found') || profileError.includes('404');
    if (isNotFound) {
      return (
        <div className="p-6">
          <InlineNotification
            kind="info"
            title="尚未建立個人資料"
            subtitle="請先登入以查看個人資料"
            hideCloseButton
          />
        </div>
      );
    }
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

  const cardStyle: React.CSSProperties = {
    background: 'var(--bg-secondary, #fff)',
    borderRadius: 'var(--radius-lg, 12px)',
    border: '1px solid var(--border)',
    padding: '1.25rem',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  };
  const cardTitle: React.CSSProperties = {
    fontSize: '1rem', fontWeight: 600, margin: '0 0 1rem', color: 'var(--text-primary)',
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Notifications */}
      {successMessage && (
        <div style={{ marginBottom: '1rem' }}>
          <InlineNotification kind="success" title="Success" subtitle={successMessage} onCloseButtonClick={() => setSuccessMessage(null)} />
        </div>
      )}
      {validationError && (
        <div style={{ marginBottom: '1rem' }}>
          <InlineNotification kind="error" title="Validation Error" subtitle={validationError} hideCloseButton />
        </div>
      )}

      {/* Card grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>

        {/* Avatar Card */}
        <div style={{ ...cardStyle, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <h3 style={cardTitle}>頭像</h3>
          <AvatarUploader />
        </div>

        {/* Personal Info Card */}
        <div style={cardStyle}>
          <h3 style={cardTitle}>個人資訊</h3>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">顯示名稱</label>
            <input
              type="text"
              className="form-input"
              style={{ width: '100%' }}
              placeholder="輸入顯示名稱"
              value={displayName}
              onChange={handleDisplayNameChange}
              disabled={isSaving}
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'block' }}>2-50 字元</span>
          </div>
          <div className="form-group">
            <label className="form-label">電子郵件</label>
            <input
              type="text"
              className="form-input"
              style={{ width: '100%', opacity: 0.6 }}
              value={profile.email}
              readOnly
              disabled
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'block' }}>電子郵件無法修改</span>
          </div>
        </div>

        {/* Account Info Card */}
        <div style={cardStyle}>
          <h3 style={cardTitle}>帳戶資訊</h3>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">帳戶等級</label>
            <input
              type="text"
              className="form-input"
              style={{ width: '100%', opacity: 0.6 }}
              value={profile.account_level === 'free' ? '免費版' : profile.account_level === 'pro' ? '專業版' : '企業版'}
              readOnly
              disabled
            />
          </div>
          <div className="form-group">
            <label className="form-label">建立時間</label>
            <input
              type="text"
              className="form-input"
              style={{ width: '100%', opacity: 0.6 }}
              value={profile.created_at ? new Date(profile.created_at).toLocaleDateString('zh-TW', { year: 'numeric', month: 'long', day: 'numeric' }) : ''}
              readOnly
              disabled
            />
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div style={{ marginTop: '1rem' }}>
        <Button type="submit" kind="primary" renderIcon={Save} disabled={!isFormValid || !hasChanges || isSaving}>
          {isSaving ? '儲存中...' : '儲存變更'}
        </Button>
        {hasChanges && !isSaving && (
          <span style={{ marginLeft: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>有未儲存的變更</span>
        )}
      </div>
    </form>
  );
}
