import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Generate initials from a name string
 * Takes the first letter of each word, maximum 2 letters
 *
 * Examples:
 * - "John Doe" -> "JD"
 * - "Alice" -> "A"
 * - "Mary Jane Watson" -> "MJ" (first two words only)
 * - "john doe" -> "JD" (case insensitive, returns uppercase)
 *
 * @param name - Full name or display name
 * @returns Initials (1-2 uppercase letters)
 */
export function generateInitials(name: string): string {
  if (!name || !name.trim()) {
    return '?';
  }

  // Split by whitespace and filter out empty strings
  const words = name.trim().split(/\s+/).filter(word => word.length > 0);

  if (words.length === 0) {
    return '?';
  }

  // Take first letter of first two words
  const initials = words
    .slice(0, 2)
    .map(word => word[0].toUpperCase())
    .join('');

  return initials;
}
