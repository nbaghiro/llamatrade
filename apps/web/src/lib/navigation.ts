/** App destinations and which one a path belongs to. */

export type DestinationKey =
  | 'home'
  | 'portfolio'
  | 'strategies'
  | 'backtests'
  | 'sessions'
  | 'copilot'
  | 'account';

export interface Destination {
  key: DestinationKey;
  label: string;
  to: string;
  /** Path prefixes that belong to this destination. */
  match: readonly string[];
}

export const DESKTOP_NAV: readonly Destination[] = [
  { key: 'home', label: 'Home', to: '/dashboard', match: ['/dashboard'] },
  { key: 'portfolio', label: 'Portfolio', to: '/portfolio', match: ['/portfolio', '/wallet'] },
  { key: 'strategies', label: 'Strategies', to: '/strategies', match: ['/strategies'] },
  { key: 'backtests', label: 'Backtests', to: '/backtests', match: ['/backtest', '/backtests'] },
  { key: 'sessions', label: 'Sessions', to: '/trading', match: ['/trading', '/sessions'] },
  { key: 'copilot', label: 'Copilot', to: '/copilot', match: ['/copilot'] },
];

/** Phones fold Sessions into Portfolio and Backtests into Strategies, and add Account. */
export const MOBILE_TABS: readonly Destination[] = [
  DESKTOP_NAV[0],
  { ...DESKTOP_NAV[1], match: [...DESKTOP_NAV[1].match, '/trading', '/sessions'] },
  {
    key: 'strategies',
    label: 'Strategies',
    to: '/strategies',
    match: ['/strategies', '/backtest', '/backtests'],
  },
  DESKTOP_NAV[5],
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
