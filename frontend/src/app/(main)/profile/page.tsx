'use client';

import ProfileForm from '@/components/profile/ProfileForm';
import { UserAvatar } from '@carbon/icons-react';

export default function ProfilePage() {
  return (
    <div className="p-4 sm:p-6 md:p-8" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      {/* Page Header */}
      <div className="mb-6 md:mb-8">
        <div className="flex items-center gap-3 mb-2">
          <UserAvatar size={32} className="text-blue-600" style={{ flexShrink: 0 }} />
          <h1 className="text-xl sm:text-2xl md:text-3xl font-semibold">Profile Settings</h1>
        </div>
        <p className="text-gray-600 text-sm sm:text-base">
          Manage your profile information and account settings
        </p>
      </div>

      {/* Profile Form - full width on mobile */}
      <div style={{ width: '100%' }}>
        <ProfileForm />
      </div>
    </div>
  );
}
