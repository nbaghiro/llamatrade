/** App destinations and which one a path belongs to. */

export type DestinationKey =
  | 'home'
  | 'markets'
  | 'portfolio'
  | 'strategies'
  | 'backtests'
  | 'sessions'
  | 'activity'
  | 'account';

export interface Destination {
  key: DestinationKey;
  label: string;
  to: string;
  /** Path prefixes that belong to this destination. */
  match: readonly string[];
}

/** Every area with a page of its own, Markets included. */
export const AREAS: readonly Destination[] = [
  { key: 'home', label: 'Home', to: '/dashboard', match: ['/dashboard', '/copilot'] },
  { key: 'markets', label: 'Markets', to: '/markets', match: ['/markets'] },
  { key: 'strategies', label: 'Strategies', to: '/strategies', match: ['/strategies'] },
  { key: 'backtests', label: 'Backtests', to: '/backtests', match: ['/backtest', '/backtests'] },
  { key: 'sessions', label: 'Sessions', to: '/trading', match: ['/trading', '/sessions'] },
  { key: 'portfolio', label: 'Portfolio', to: '/portfolio', match: ['/portfolio', '/wallet'] },
];

const byKey = (key: DestinationKey): Destination => {
  const d = AREAS.find((n) => n.key === key);
  if (!d) throw new Error(`Unknown destination ${key}`);
  return d;
};

/** Five areas in the bar; Home is the Copilot chat, and the market status leads to Markets. */
export const DESKTOP_NAV: readonly Destination[] = AREAS.filter((d) => d.key !== 'markets');

export const MARKETS: Destination = byKey('markets');

/** Backtests sit inside Strategies on a phone; Account and Activity sit behind the avatar and the bell. */
export const MOBILE_TABS: readonly Destination[] = [
  byKey('home'),
  MARKETS,
  byKey('sessions'),
  { ...byKey('strategies'), match: ['/strategies', '/backtest', '/backtests'] },
  byKey('portfolio'),
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
