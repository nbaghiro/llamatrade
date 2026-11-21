import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '@llamatrade/core/billing/planTiers';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useEffect, useMemo } from 'react';

import { useAppearanceStore } from '../stores/appearance';
import { useTheme } from '../theme';
import { accountHealth, healthSummary, problemText, type AccountHealth, type HealthSession, type HealthSummary } from './health';
import { emailSummary } from './notificationModel';
import { ROUTING } from './notifications';

export interface SectionState {
  text: string;
  risk?: boolean;
}

export interface AccountSummary {
  health: AccountHealth;
  summary: HealthSummary;
  brokerLoaded: boolean;
  broker: SectionState | null;
  notifications: SectionState;
  appearance: SectionState;
  plan: SectionState | null;
  /** Running sessions per account, for the connection rows. */
  sessions: HealthSession[];
}

const MODE_LABEL = { system: 'System', light: 'Light', dark: 'Dark' } as const;

/** What the broker, plan, notification, theme and dashboard stores know, loading what's missing. */
export function useAccountSummary(): AccountSummary {
  const credentials = useBrokerStore((s) => s.credentials);
  const brokerLoaded = useBrokerStore((s) => s.loaded);
  const lastCheck = useBrokerStore((s) => s.lastCheck);
  const fetchBroker = useBrokerStore((s) => s.fetch);
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const preferences = useNotificationsStore((s) => s.preferences);
  const fetchPreferences = useNotificationsStore((s) => s.fetchPreferences);
  const strategies = useDashboardStore((s) => s.strategies);
  const dashboardLoaded = useDashboardStore((s) => s.loaded);
  const dashboardLoading = useDashboardStore((s) => s.loading);
  const fetchDashboard = useDashboardStore((s) => s.fetchDashboard);
  const modePref = useAppearanceStore((s) => s.mode);
  const { mode } = useTheme();

  useEffect(() => {
    fetchBroker().catch(() => undefined);
    fetchSubscription().catch(() => undefined);
    fetchPreferences().catch(() => undefined);
  }, [fetchBroker, fetchSubscription, fetchPreferences]);

  useEffect(() => {
    if (!dashboardLoaded && !dashboardLoading) fetchDashboard().catch(() => undefined);
  }, [dashboardLoaded, dashboardLoading, fetchDashboard]);

  return useMemo(() => {
    const sessions: HealthSession[] = strategies.map((st) => ({
      name: st.name,
      kind: st.mode === ExecutionMode.LIVE ? 'live' : 'paper',
      running: st.status === ExecutionStatus.RUNNING,
      // The API has no next-run time per session yet.
      nextRun: null,
    }));
    const health = accountHealth(
      credentials,
      lastCheck ? { at: lastCheck.at, valid: lastCheck.valid, isPaper: lastCheck.isPaper, message: lastCheck.message } : null,
      sessions,
    );
    const problem = health.problems[0];
    const tier = resolveCurrentTier(subscription);
    const broker: SectionState | null = !brokerLoaded
      ? null
      : problem
        ? { text: problemText(problem).short, risk: true }
        : health.connected.length > 0
          ? { text: 'Connected' }
          : { text: 'Not connected' };
    const appearance = modePref === 'system' ? `System, ${mode}` : MODE_LABEL[modePref];
    return {
      health,
      summary: healthSummary(health),
      brokerLoaded,
      broker,
      notifications: { text: emailSummary(ROUTING, preferences) },
      appearance: { text: appearance },
      plan: tier ? { text: `${PLAN_TIER_BY_KEY[tier].name}${subscription?.isBeta ? ' · beta' : ''}` } : null,
      sessions,
    };
  }, [strategies, credentials, lastCheck, subscription, brokerLoaded, preferences, modePref, mode]);
}
