/** What needs the person, pinned to the tab where it is resolved (attention2 A). */

export interface NamedItem {
  id: string;
  name: string;
}

export interface SessionsAttention {
  /** Frozen sleeves and rejected orders, without duplicates. */
  count: number;
  frozen: readonly NamedItem[];
  /** Spoken label for the Sessions tab. */
  label: string;
}

function unique(items: readonly NamedItem[]): NamedItem[] {
  const seen = new Set<string>();
  return items.filter((i) => !seen.has(i.id) && (seen.add(i.id), true));
}

/**
 * Frozen sleeves (from Home's read and the trading store's, either may be missing) and recent
 * rejected orders all live under Sessions, so they mark that one tab.
 */
export function sessionsAttention(
  dashboardFrozen: readonly NamedItem[] | null,
  tradingFrozen: readonly NamedItem[],
  rejected: readonly NamedItem[] | null,
): SessionsAttention {
  const frozen = unique([...(dashboardFrozen ?? []), ...tradingFrozen]);
  const count = frozen.length + unique(rejected ?? []).length;
  const label = count === 0 ? 'Sessions' : `Sessions, ${count} ${count === 1 ? 'needs' : 'need'} attention`;
  return { count, frozen, label };
}
