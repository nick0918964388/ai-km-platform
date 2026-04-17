'use client';

import { generateInitials } from '@/lib/utils';

interface AccountInitialsProps {
  /** Display name to generate initials from */
  displayName: string;
  /** Size of the badge in pixels (default: 40) */
  size?: number;
  /** Additional CSS classes */
  className?: string;
  /** Background color (default: gradient blue) */
  backgroundColor?: string;
  /** Text color (default: white) */
  textColor?: string;
}

/**
 * AccountInitials Component
 * Displays user initials in a circular badge as an avatar fallback
 *
 * Features:
 * - Generates 1-2 letter initials from display name
 * - Circular badge with gradient background
 * - Customizable size and colors
 * - Accessible with proper contrast
 */
export default function AccountInitials({
  displayName,
  size = 40,
  className = '',
  backgroundColor,
  textColor = 'white',
}: AccountInitialsProps) {
  const initials = generateInitials(displayName);

  // Default gradient background
  const defaultBg = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  const bgStyle = backgroundColor || defaultBg;

  return (
    <div
      className={`flex items-center justify-center rounded-full font-semibold select-none ${className}`}
      style={{
        width: size,
        height: size,
        background: bgStyle,
        color: textColor,
        fontSize: size * 0.4, // Font size is 40% of container size
        lineHeight: 1,
      }}
      role="img"
      aria-label={`Avatar for ${displayName}`}
      title={displayName}
    >
      {initials}
    </div>
  );
}
