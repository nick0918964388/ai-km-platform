'use client';

import ProfileForm from '@/components/profile/ProfileForm';
import { UserAvatar } from '@carbon/icons-react';

export default function ProfilePage() {
  return (
    <div className="p-6 md:p-8">
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <UserAvatar size={32} className="text-blue-600" />
          <h1 className="text-2xl md:text-3xl font-semibold">Profile Settings</h1>
        </div>
        <p className="text-gray-600">
          Manage your profile information and account settings
        </p>
      </div>

      {/* Profile Form */}
      <ProfileForm />
    </div>
  );
}
