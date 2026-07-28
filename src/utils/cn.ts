// Tiny classnames joiner (no clsx dependency — spec caps runtime deps).
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
