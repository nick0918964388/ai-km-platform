'use client';

import ProfileForm from '@/components/profile/ProfileForm';

export default function ProfilePage() {
  return (
    <div style={{ padding: '1.5rem 2rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>個人資料設定</h1>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: '0.25rem 0 1.5rem' }}>管理您的個人資料與帳戶設定</p>
      <ProfileForm />
    </div>
  );
}
