import { describe, expect, it } from 'vitest';

import { activeDestination, DESKTOP_NAV, MOBILE_TABS } from '../navigation';

describe('navigation', () => {
  it('lists the six desktop destinations in order', () => {
    expect(DESKTOP_NAV.map((d) => d.label)).toEqual([
      'Home',
      'Portfolio',
      'Strategies',
      'Backtests',
      'Sessions',
      'Copilot',
    ]);
  });

  it('lists the five phone tabs in order', () => {
    expect(MOBILE_TABS.map((d) => d.label)).toEqual([
      'Home',
      'Portfolio',
      'Strategies',
      'Copilot',
      'Account',
    ]);
  });

  it('matches nested paths but not lookalike prefixes', () => {
    expect(activeDestination('/strategies/abc', DESKTOP_NAV)).toBe('strategies');
    expect(activeDestination('/strategiesx', DESKTOP_NAV)).toBeNull();
    expect(activeDestination('/dashboard', DESKTOP_NAV)).toBe('home');
    expect(activeDestination('/settings', DESKTOP_NAV)).toBeNull();
  });

  it('folds backtests into Strategies and sessions into Portfolio on phones', () => {
    expect(activeDestination('/backtest', DESKTOP_NAV)).toBe('backtests');
    expect(activeDestination('/backtest', MOBILE_TABS)).toBe('strategies');
    expect(activeDestination('/trading', MOBILE_TABS)).toBe('portfolio');
    expect(activeDestination('/trading/orders/o1', MOBILE_TABS)).toBe('portfolio');
    expect(activeDestination('/billing/subscribe', MOBILE_TABS)).toBe('account');
  });
});
