import { Bell, CreditCard, Palette, PlugZap, User, type LucideIcon } from 'lucide-react';

export type SectionKey = 'profile' | 'broker' | 'notifications' | 'appearance' | 'plan';

export interface SectionEntry {
  key: SectionKey;
  label: string;
  icon: LucideIcon;
}

export interface SectionGroup {
  label: string;
  items: readonly SectionEntry[];
}

export const SECTION_GROUPS: readonly SectionGroup[] = [
  {
    label: 'Account',
    items: [
      { key: 'profile', label: 'Profile and security', icon: User },
      { key: 'broker', label: 'Broker', icon: PlugZap },
    ],
  },
  {
    label: 'Preferences',
    items: [
      { key: 'notifications', label: 'Notifications', icon: Bell },
      { key: 'appearance', label: 'Appearance', icon: Palette },
    ],
  },
  {
    label: 'Billing',
    items: [{ key: 'plan', label: 'Plan and usage', icon: CreditCard }],
  },
];

export const SECTIONS: readonly SectionEntry[] = SECTION_GROUPS.flatMap((g) => g.items);

export const DEFAULT_SECTION: SectionKey = 'profile';

/** Old ?tab= values and aliases that still open the right section. */
const ALIASES: Readonly<Record<string, SectionKey>> = {
  billing: 'plan',
  security: 'profile',
  keys: 'broker',
};

export function sectionPath(key: SectionKey): string {
  return `/settings/${key}`;
}

/** The section a URL segment or legacy ?tab= value names, or null when it names none. */
export function resolveSection(raw: string | null | undefined): SectionKey | null {
  if (!raw) return null;
  const value = raw.trim().toLowerCase();
  return SECTIONS.find((s) => s.key === value)?.key ?? ALIASES[value] ?? null;
}

export function sectionLabel(key: SectionKey): string {
  return SECTIONS.find((s) => s.key === key)?.label ?? '';
}
