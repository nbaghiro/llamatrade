/** App destinations and which one a path belongs to. */

export type DestinationKey =
  | 'home'
  | 'markets'
  | 'portfolio'
  | 'strategies'
  | 'backtests'
  | 'sessions'
  | 'copilot'
  | 'activity'
  | 'account';

export interface Destination {
  key: DestinationKey;
  label: string;
  to: string;
  /** Path prefixes that belong to this destination. */
  match: readonly string[];
}

/** Seven areas, Markets second because prices are checked most days (frame2 A). */
export const DESKTOP_NAV: readonly Destination[] = [
  { key: 'home', label: 'Home', to: '/dashboard', match: ['/dashboard'] },
  { key: 'markets', label: 'Markets', to: '/markets', match: ['/markets'] },
  { key: 'strategies', label: 'Strategies', to: '/strategies', match: ['/strategies'] },
  { key: 'backtests', label: 'Backtests', to: '/backtests', match: ['/backtest', '/backtests'] },
  { key: 'sessions', label: 'Sessions', to: '/trading', match: ['/trading', '/sessions'] },
  { key: 'portfolio', label: 'Portfolio', to: '/portfolio', match: ['/portfolio', '/wallet'] },
  { key: 'copilot', label: 'Copilot', to: '/copilot', match: ['/copilot'] },
];

const byKey = (key: DestinationKey): Destination => {
  const d = DESKTOP_NAV.find((n) => n.key === key);
  if (!d) throw new Error(`Unknown destination ${key}`);
  return d;
};

/** Phones are for checking in (phone-nav2 D); building stays on the web. */
export const MOBILE_TABS: readonly Destination[] = [
  byKey('home'),
  byKey('sessions'),
  byKey('markets'),
  { key: 'activity', label: 'Activity', to: '/notifications', match: ['/notifications'] },
  { key: 'account', label: 'Account', to: '/settings', match: ['/settings', '/billing'] },
];

function under(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** The destination whose prefixes contain `pathname`, if any. */
export function activeDestination(
  pathname: string,
  list: readonly Destination[]
): DestinationKey | null {
  return list.find((d) => d.match.some((p) => under(pathname, p)))?.key ?? null;
}
