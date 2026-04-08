'use client';

import ProfileForm from '@/components/profile/ProfileForm';
import { UserAvatar } from '@carbon/icons-react';

export default function ProfilePage() {
  return (
    <div className="p-4 sm:p-6 md:p-8" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      {/* Page Header */}
      <div className="mb-6 md:mb-8">
        <div className="flex items-center gap-3 mb-2">
          <UserAvatar size={32} style={{ flexShrink: 0, color: 'var(--primary)' }} />
          <h1 className="text-xl sm:text-2xl md:text-3xl font-semibold">個人資料設定</h1>
        </div>
        <p className="text-sm sm:text-base" style={{ color: 'var(--text-secondary)' }}>
          管理您的個人資料與帳戶設定
        </p>
      </div>

      {/* Profile Form - full width on mobile */}
      <div style={{ width: '100%' }}>
        <ProfileForm />
      </div>
    </div>
  );
}
