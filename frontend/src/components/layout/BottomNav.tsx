'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Chat, Dashboard, RecentlyViewed, UserAvatar } from '@carbon/icons-react';
import { useStore } from '@/store/useStore';

const navItems = [
  { href: '/chat', label: 'AI 問答', icon: Chat },
  { href: '/dashboard', label: '儀表板', icon: Dashboard },
  { href: '/history', label: '紀錄', icon: RecentlyViewed },
  { href: '/profile', label: '個人', icon: UserAvatar },
];

export default function BottomNav() {
  const pathname = usePathname();
  const { user } = useStore();

  // Hide bottom nav on chat page for more screen space
  if (!user || pathname === '/chat' || pathname.startsWith('/chat/')) return null;

  return (
    <nav className="bottom-nav" aria-label="底部導航">
      {navItems.map(({ href, label, icon: Icon }) => {
        const isActive = pathname === href || pathname.startsWith(href + '/');
        return (
          <Link
            key={href}
            href={href}
            className={`bottom-nav-item${isActive ? ' active' : ''}`}
            aria-current={isActive ? 'page' : undefined}
          >
            <span className="bottom-nav-icon">
              <Icon size={22} />
            </span>
            <span className="bottom-nav-label">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
