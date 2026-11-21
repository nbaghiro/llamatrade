/** The five phone tabs (phone-nav2 A), matching the web phone bar's order. */

export type TabKey = 'index' | 'markets' | 'sessions' | 'strategies' | 'copilot';

export interface TabSpec {
  /** Route file under app/(tabs). */
  name: TabKey;
  title: string;
}

export const TABS: readonly TabSpec[] = [
  { name: 'index', title: 'Home' },
  { name: 'markets', title: 'Markets' },
  { name: 'sessions', title: 'Sessions' },
  { name: 'strategies', title: 'Strategies' },
  { name: 'copilot', title: 'Copilot' },
];

/** Up to two initials for the header avatar, from the name or else the email. */
export function initials(user: { firstName?: string; lastName?: string; email?: string } | null | undefined): string {
  const first = user?.firstName?.trim() ?? '';
  const last = user?.lastName?.trim() ?? '';
  const fromName = `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
  if (fromName) return fromName;
  const local = user?.email?.split('@')[0] ?? '';
  const parts = local.split(/[._-]+/).filter(Boolean);
  const fromEmail = parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : local.slice(0, 2);
  return fromEmail.toUpperCase() || '?';
}
