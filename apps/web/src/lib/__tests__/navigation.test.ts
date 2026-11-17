import { describe, expect, it } from 'vitest';

import { activeDestination, DESKTOP_NAV, MOBILE_TABS } from '../navigation';

describe('navigation', () => {
  it('lists the seven desktop areas with Markets second', () => {
    expect(DESKTOP_NAV.map((d) => d.label)).toEqual([
      'Home',
      'Markets',
      'Strategies',
      'Backtests',
      'Sessions',
      'Portfolio',
      'Copilot',
    ]);
  });

  it('lists the five phone tabs for checking in', () => {
    expect(MOBILE_TABS.map((d) => d.label)).toEqual([
      'Home',
      'Sessions',
      'Markets',
      'Activity',
      'Account',
    ]);
  });

  it('matches nested paths but not lookalike prefixes', () => {
    expect(activeDestination('/strategies/abc', DESKTOP_NAV)).toBe('strategies');
    expect(activeDestination('/strategiesx', DESKTOP_NAV)).toBeNull();
    expect(activeDestination('/dashboard', DESKTOP_NAV)).toBe('home');
    expect(activeDestination('/markets', DESKTOP_NAV)).toBe('markets');
    expect(activeDestination('/settings', DESKTOP_NAV)).toBeNull();
  });

  it('maps phone paths to their tabs, leaving building areas without one', () => {
    expect(activeDestination('/trading/orders/o1', MOBILE_TABS)).toBe('sessions');
    expect(activeDestination('/notifications', MOBILE_TABS)).toBe('activity');
    expect(activeDestination('/billing/subscribe', MOBILE_TABS)).toBe('account');
    expect(activeDestination('/strategies/abc', MOBILE_TABS)).toBeNull();
  });
});
