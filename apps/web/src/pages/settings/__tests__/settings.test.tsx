import { PLAN_TIER_BY_KEY } from '@llamatrade/core/billing/planTiers';
import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import type { Subscription } from '@llamatrade/core/proto/billing_pb';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { planLabel } from '../../../components/billing/format';
import {
  alpacaSignIn,
  displayName,
  identityLine,
  keyMismatch,
  planLine,
  primaryCredential,
} from '../model';
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
    ['/settings/broker', 'Broker', 'aria-busy="true"'],
    ['/settings/notifications', 'Notifications', 'Delivery'],
    ['/settings/appearance', 'Appearance', 'Graphite'],
    ['/settings/plan', 'Plan and usage', 'Invoices'],
  ])('opens %s with only its tab selected', (path, label, content) => {
    const html = render(path);
    const start = html.indexOf('aria-label="Settings"');
    const tablist = html.slice(start, html.indexOf('</div>', start));
    const selected = tablist.match(/aria-selected="true"[^>]*>([^<]+)</g) ?? [];
    expect(selected).toHaveLength(1);
    expect(selected[0]).toContain(label);
    expect(tablist.match(/role="tab"/g)).toHaveLength(5);
    expect(html).toContain(content);
  });

  it('opens the section a legacy ?tab= names', () => {
    const html = render('/settings?tab=billing');
    expect(html).toMatch(/aria-selected="true"[^>]*>Plan and usage</);
  });

  it('puts the person and Sign out above the tabs', () => {
    const html = render('/settings/profile');
    expect(html.indexOf('Sign out')).toBeLessThan(html.indexOf('role="tablist"'));
    expect(html).toContain('Workspace');
  });

  it('lists Alpaca sign-in under Security while the account is read', () => {
    const html = render('/settings/profile');
    expect(html.indexOf('Alpaca sign-in')).toBeGreaterThan(html.indexOf('Security'));
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

  it('writes the header line from whatever is known', () => {
    const since = new Date(2026, 8, 14);
    expect(
      identityLine({ email: 'sam@example.com', workspace: 'Rivera', memberSince: since })
    ).toBe('sam@example.com · Rivera workspace · member since September 2026');
    expect(identityLine({ email: 'sam@example.com', workspace: '  ', memberSince: null })).toBe(
      'sam@example.com'
    );
    expect(identityLine({})).toBe('');
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

  it('shows the closed beta at no charge, and an ending beta as ending', () => {
    const beta = planLine(sub({ isBeta: true }), PLAN_TIER_BY_KEY.pro);
    expect(beta).toMatchObject({
      badge: 'Closed beta',
      note: 'No charge during the closed beta.',
      amount: '$0',
      ending: false,
    });
    const ending = planLine(sub({ isBeta: true, cancelAtPeriodEnd: true }), PLAN_TIER_BY_KEY.pro);
    expect(ending.badge).toBe('Ending');
  });

  it('adds the closed beta to the plan name only when the subscription is in it', () => {
    expect(planLabel('Pro', true)).toBe('Pro · closed beta');
    expect(planLabel('Pro', false)).toBe('Pro');
    expect(planLabel('Pro', undefined)).toBe('Pro');
  });

  it('describes Alpaca sign-in when linked, not linked and unknown', () => {
    expect(alpacaSignIn(true)).toEqual({
      sub: 'Linked. You can sign in with Alpaca or your password.',
      status: 'Linked',
    });
    expect(alpacaSignIn(false).status).toBe('Not linked');
    expect(alpacaSignIn(null)).toEqual({ sub: "Couldn't be checked just now.", status: null });
  });

  it('falls back to the tier name and price when the plan carries none', () => {
    const bare = { plan: undefined, cancelAtPeriodEnd: false } as unknown as Subscription;
    const line = planLine(bare, PLAN_TIER_BY_KEY.pro);
    expect(line.name).toBe('Pro');
    expect(line.amount).toBe('$49');
  });
});
