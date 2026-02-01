'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useStore } from '@/store/useStore';

export default function Home() {
  const router = useRouter();
  const { user } = useStore();

  useEffect(() => {
    if (user) {
      router.push('/chat');
    } else {
      router.push('/login');
    }
  }, [user, router]);

  return (
    <div style={{
      height: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-secondary)'
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 64,
          height: 64,
          background: 'var(--primary)',
          borderRadius: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: '1.5rem',
          fontWeight: 700,
          margin: '0 auto 1rem',
          animation: 'pulse 1.5s infinite'
        }}>
          KM
        </div>
        <p style={{ color: 'var(--text-secondary)' }}>載入中...</p>
      </div>
      <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}
