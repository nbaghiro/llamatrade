import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '@llamatrade/core/billing/planTiers';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { ChannelType } from '@llamatrade/core/proto/notification_pb';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useEffect, useMemo } from 'react';

import { useSessionRows } from '../../components/shell/useSessionRows';
import { nextRebalanceDate } from '../../lib/sessionState';
import { useThemeStore } from '../../store/theme';

import {
  accountHealth,
  healthSummary,
  problemText,
  type AccountHealth,
  type HealthSession,
  type HealthSummary,
} from './health';
import type { SectionKey } from './sections';

export interface SectionState {
  text: string;
  risk?: boolean;
}

export interface SettingsSummary {
  health: AccountHealth;
  summary: HealthSummary;
  /** The short state beside each section in the sidebar and the lists (shell2 A). */
  states: Record<SectionKey, SectionState | null>;
  brokerLoaded: boolean;
}

const MODE_LABEL = { system: 'System', light: 'Light', dark: 'Dark' } as const;

/** Reads what the broker, plan, notification and theme stores know, and loads what's missing. */
export function useSettingsSummary(): SettingsSummary {
  const credentials = useBrokerStore((s) => s.credentials);
  const brokerLoaded = useBrokerStore((s) => s.loaded);
  const lastCheck = useBrokerStore((s) => s.lastCheck);
  const fetchBroker = useBrokerStore((s) => s.fetch);
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const preferences = useNotificationsStore((s) => s.preferences);
  const fetchPreferences = useNotificationsStore((s) => s.fetchPreferences);
  const mode = useThemeStore((s) => s.mode);
  const rows = useSessionRows();

  useEffect(() => {
    fetchBroker().catch(() => undefined);
    fetchSubscription().catch(() => undefined);
    fetchPreferences().catch(() => undefined);
  }, [fetchBroker, fetchSubscription, fetchPreferences]);

  return useMemo(() => {
    const now = new Date();
    const sessions: HealthSession[] = rows.map((r) => ({
      name: r.name,
      kind: r.session.mode === ExecutionMode.LIVE ? 'live' : 'paper',
      running: r.session.isActive,
      nextRun: nextRebalanceDate(r.rebalance, now),
    }));
    const health = accountHealth(credentials, lastCheck, sessions);
    const problem = health.problems[0];
    const email = preferences.find((p) => p.channel === ChannelType.EMAIL);
    const tier = resolveCurrentTier(subscription);

    const broker: SectionState | null = !brokerLoaded
      ? null
      : problem
        ? { text: problemText(problem).short, risk: true }
        : health.connected.length > 0
          ? { text: 'Connected' }
          : { text: 'Not connected' };

    return {
      health,
      summary: healthSummary(health),
      brokerLoaded,
      states: {
        profile: null,
        broker,
        notifications: { text: email && !email.enabled ? 'Email off' : 'Email on' },
        appearance: { text: MODE_LABEL[mode] },
        plan: tier ? { text: PLAN_TIER_BY_KEY[tier].name } : null,
      },
    };
  }, [rows, credentials, lastCheck, preferences, subscription, brokerLoaded, mode]);
}
