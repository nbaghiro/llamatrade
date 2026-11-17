import { PLAN_TIER_BY_KEY } from '@llamatrade/core/billing/planTiers';
import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import type { Subscription } from '@llamatrade/core/proto/billing_pb';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { displayName, keyMismatch, planLine, primaryCredential } from '../model';
import { SECTION_GROUPS, SECTIONS, resolveSection, sectionPath } from '../sections';
import SettingsPage from '../SettingsPage';

const render = (path: string) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/:section" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>
  );

describe('section routing', () => {
  it.each([
    ['profile', 'profile'],
    ['broker', 'broker'],
    ['notifications', 'notifications'],
    ['appearance', 'appearance'],
    ['plan', 'plan'],
    ['Plan', 'plan'],
    [' broker ', 'broker'],
    ['billing', 'plan'],
    ['security', 'profile'],
    ['keys', 'broker'],
  ])('resolves %j to %s', (raw, key) => {
    expect(resolveSection(raw)).toBe(key);
  });

  it.each([null, undefined, '', 'plans', 'wallet', '../profile'])(
    'resolves %j to no section',
    (raw) => {
      expect(resolveSection(raw)).toBeNull();
    }
  );

  it('gives each section its own URL, in grouped order', () => {
    expect(SECTIONS.map((s) => sectionPath(s.key))).toEqual([
      '/settings/profile',
      '/settings/broker',
      '/settings/notifications',
      '/settings/appearance',
      '/settings/plan',
    ]);
    expect(SECTION_GROUPS.map((g) => g.label)).toEqual(['Account', 'Preferences', 'Billing']);
  });

  it.each([
    ['/settings/profile', 'Profile and security', 'Read only for now'],
    ['/settings/broker', 'Broker', 'Settings'],
    ['/settings/notifications', 'Notifications', 'Delivery'],
    ['/settings/appearance', 'Appearance', 'Saved on this device'],
    ['/settings/plan', 'Plan and usage', 'Invoices'],
  ])('opens %s with only its sidebar item current', (path, label, content) => {
    const html = render(path);
    const current =
      html.match(/aria-current="page"[^>]*>(?:<svg.*?<\/svg>)?(?:<span[^>]*>)?([^<]+)</g) ?? [];
    expect(current).toHaveLength(1);
    expect(current[0]).toContain(label);
    expect(html).toContain(content);
  });

  it('opens the section a legacy ?tab= names', () => {
    const html = render('/settings?tab=billing');
    expect(html).toMatch(
      /aria-current="page"[^>]*>(?:<svg.*?<\/svg>)?(?:<span[^>]*>)?Plan and usage</
    );
  });

  it('shows the Account list at /settings on a phone', () => {
    const html = render('/settings');
    expect(html).toContain('>Account</h1>');
    for (const s of SECTIONS) expect(html).toContain(`href="${sectionPath(s.key)}"`);
    expect(html).toContain('Sign out');
    expect(html).not.toContain('aria-label="Settings"');
  });

  it('renders nothing for an unknown section while it redirects', () => {
    expect(render('/settings/wallet')).toBe('');
  });
});

describe('settings view models', () => {
  const cred = (id: string, isActive: boolean) =>
    ({ id, isActive, apiKeyPrefix: 'PK7Q', isPaper: true, name: '' }) as AlpacaCredentialsListItem;

  it('shows an active credential first, then any', () => {
    expect(primaryCredential([cred('a', false), cred('b', true)])?.id).toBe('b');
    expect(primaryCredential([cred('a', false)])?.id).toBe('a');
    expect(primaryCredential([])).toBeNull();
  });

  it('only checks a pasted key that matches the one in use', () => {
    expect(keyMismatch('  ', 'PK7Q')).toBe('Enter the key ID.');
    expect(keyMismatch('PKZZ123', 'PK7Q')).toContain('PK7Q••••');
    expect(keyMismatch(' PK7Q123 ', 'PK7Q')).toBeNull();
    expect(keyMismatch('anything', '')).toBeNull();
  });

  it('builds a display name from whichever parts exist', () => {
    expect(displayName({ firstName: ' Sam ', lastName: 'Rivera' })).toBe('Sam Rivera');
    expect(displayName({ firstName: '', lastName: 'Rivera' })).toBe('Rivera');
    expect(displayName(null)).toBe('');
  });

  const sub = (extra: Partial<Subscription> = {}) =>
    ({
      plan: { monthlyPrice: { amount: '49', currency: 'USD' } },
      currentPrice: { amount: '49', currency: 'USD' },
      currentPeriodEnd: { seconds: BigInt(Date.UTC(2026, 11, 1, 12) / 1000), nanos: 0 },
      cancelAtPeriodEnd: false,
      ...extra,
    }) as unknown as Subscription;

  it('shows the monthly charge and next invoice', () => {
    const line = planLine(sub(), PLAN_TIER_BY_KEY.pro);
    expect(line.amount).toBe('$49');
    expect(line.note).toBe('Billed monthly. Next invoice Dec 1, 2026.');
    expect(line.badge).toBeNull();
  });

  it('shows the trial and what follows it', () => {
    const trial = planLine(
      sub({
        isTrial: true,
        trialEnd: { seconds: BigInt(Date.UTC(2026, 11, 1, 12) / 1000), nanos: 0 },
      } as Partial<Subscription>),
      PLAN_TIER_BY_KEY.pro
    );
    expect(trial).toMatchObject({ badge: 'Trial', amount: '$0' });
    expect(trial.note).toBe('Trial ends Dec 1, 2026. Then $49 a month.');
  });

  it('shows no charge once cancelled, and on a free plan', () => {
    const ending = planLine(sub({ cancelAtPeriodEnd: true }), PLAN_TIER_BY_KEY.pro);
    expect(ending).toMatchObject({ badge: 'Ending', amount: '$0', ending: true });
    const free = {
      plan: { name: 'Free', monthlyPrice: { amount: '0', currency: 'USD' } },
      currentPrice: { amount: '0', currency: 'USD' },
      cancelAtPeriodEnd: false,
    } as unknown as Subscription;
    expect(planLine(free, PLAN_TIER_BY_KEY.free)).toMatchObject({
      name: 'Free',
      amount: '$0',
      badge: null,
    });
  });

  it('falls back to the tier name and price when the plan carries none', () => {
    const bare = { plan: undefined, cancelAtPeriodEnd: false } as unknown as Subscription;
    const line = planLine(bare, PLAN_TIER_BY_KEY.pro);
    expect(line.name).toBe('Pro');
    expect(line.amount).toBe('$49');
  });
});
