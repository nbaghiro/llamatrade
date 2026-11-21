import { describe, expect, it } from 'vitest';

import { activeDestination, AREAS, DESKTOP_NAV, MARKETS, MOBILE_TABS } from '../navigation';

describe('navigation', () => {
  it('lists five desktop areas, with Copilot as Home', () => {
    expect(DESKTOP_NAV.map((d) => d.label)).toEqual([
      'Home',
      'Strategies',
      'Backtests',
      'Sessions',
      'Portfolio',
    ]);
    expect(MARKETS.to).toBe('/markets');
  });

  it('gives Markets the second phone tab and Portfolio the last', () => {
    expect(MOBILE_TABS.map((d) => d.label)).toEqual([
      'Home',
      'Markets',
      'Sessions',
      'Strategies',
      'Portfolio',
    ]);
  });

  it('matches nested paths but not lookalike prefixes', () => {
    expect(activeDestination('/strategies/abc', DESKTOP_NAV)).toBe('strategies');
    expect(activeDestination('/strategiesx', DESKTOP_NAV)).toBeNull();
    expect(activeDestination('/dashboard', DESKTOP_NAV)).toBe('home');
    expect(activeDestination('/copilot/s1', DESKTOP_NAV)).toBe('home');
    expect(activeDestination('/markets', DESKTOP_NAV)).toBeNull();
    expect(activeDestination('/markets', AREAS)).toBe('markets');
    expect(activeDestination('/settings', DESKTOP_NAV)).toBeNull();
  });

  it('files backtests under Strategies on a phone', () => {
    expect(activeDestination('/trading/orders/o1', MOBILE_TABS)).toBe('sessions');
    expect(activeDestination('/backtests/b1', MOBILE_TABS)).toBe('strategies');
    expect(activeDestination('/portfolio', MOBILE_TABS)).toBe('portfolio');
    expect(activeDestination('/markets', MOBILE_TABS)).toBe('markets');
    expect(activeDestination('/settings', MOBILE_TABS)).toBeNull();
    expect(activeDestination('/notifications', MOBILE_TABS)).toBeNull();
  });
});
