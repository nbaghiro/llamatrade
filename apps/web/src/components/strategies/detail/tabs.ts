/** The strategy page's tabs and the older names that still open them. */

export type DetailTab = 'overview' | 'today' | 'rules' | 'performance' | 'versions';

export const TABS: ReadonlyArray<{ key: DetailTab; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'today', label: 'Would hold today' },
  { key: 'rules', label: 'Rules' },
  { key: 'performance', label: 'Performance' },
  { key: 'versions', label: 'Versions' },
];

/** Older tab names still open the closest new tab. */
const ALIASES: Record<string, DetailTab> = {
  definition: 'rules',
  backtests: 'performance',
  session: 'overview',
};

export function toTab(v: string | null | undefined): DetailTab {
  if (!v) return 'overview';
  if (TABS.some((t) => t.key === v)) return v as DetailTab;
  return ALIASES[v] ?? 'overview';
}
