import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '@llamatrade/core/billing/planTiers';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useEffect } from 'react';

import { maskedAccount } from '../../lib/scope';
import { useResolvedTheme, useThemeStore } from '../../store/theme';
import { accentsFor } from '../../theme/accents';

import type { SectionKey } from './sections';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** One line under each section's name, from what the stores already hold. */
export function useSectionDetails(): Record<SectionKey, { sub: string; value?: string }> {
  const credentials = useBrokerStore((s) => s.credentials);
  const webhooks = useNotificationsStore((s) => s.webhooks);
  const alerts = useNotificationsStore((s) => s.alerts);
  const fetchWebhooks = useNotificationsStore((s) => s.fetchWebhooks);
  const fetchAlerts = useNotificationsStore((s) => s.fetchAlerts);
  const usage = useBillingStore((s) => s.usageCounts);
  const subscription = useBillingStore((s) => s.subscription);
  const fetchUsageCounts = useBillingStore((s) => s.fetchUsageCounts);
  const mode = useThemeStore((s) => s.mode);
  const theme = useResolvedTheme();

  useEffect(() => {
    fetchWebhooks().catch(() => undefined);
    fetchAlerts().catch(() => undefined);
    fetchUsageCounts().catch(() => undefined);
  }, [fetchWebhooks, fetchAlerts, fetchUsageCounts]);

  const accounts = credentials
    .map((c) => `${c.isPaper ? 'Paper' : 'Live'} ${maskedAccount(c.accountNumber)}`.trim())
    .join(' · ');
  const tier = PLAN_TIER_BY_KEY[resolveCurrentTier(subscription) ?? 'free'];
  const backtests =
    usage && tier.limits.backtestsPerMonth > 0
      ? `${usage.backtests.toLocaleString('en-US')} of ${tier.limits.backtestsPerMonth.toLocaleString('en-US')} backtests this month`
      : 'Limits and usage this month';
  const surface = theme.mode === 'dark' ? theme.theme : theme.light;
  const accent = accentsFor(theme.mode).find((a) => a.key === theme.acc)?.label ?? '';

  return {
    profile: { sub: 'Password reset, with two-factor sign-in later' },
    broker: { sub: accounts || 'No Alpaca account connected yet' },
    notifications: {
      sub: `${plural(webhooks.length, 'webhook', 'webhooks')} · ${plural(alerts.length, 'price alert', 'price alerts')}`,
    },
    appearance: {
      sub: 'Saved on this device',
      value: [mode === 'system' ? 'System' : cap(theme.mode), cap(surface), accent]
        .filter(Boolean)
        .join(' · '),
    },
    plan: { sub: backtests },
  };
}
