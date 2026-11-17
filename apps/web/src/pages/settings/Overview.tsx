import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '@llamatrade/core/billing/planTiers';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { ChevronRight } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { PageHead } from '../../components/ui';
import { maskedKey } from '../../lib/scope';
import { useAuthStore } from '../../store/auth';
import { useResolvedTheme, useThemeStore } from '../../store/theme';
import { accentsFor } from '../../theme/accents';

import { HealthCard } from './HealthCard';
import { displayName } from './model';
import { SECTIONS, sectionPath, type SectionKey } from './sections';
import { useSettingsSummary } from './useSettingsSummary';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** One line under each section's name, from what the stores already hold. */
function useSectionDetails(): Record<SectionKey, { sub: string; value?: string }> {
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
    .map((c) => `${c.isPaper ? 'Paper' : 'Live'} ${maskedKey(c.apiKeyPrefix)}`.trim())
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

function Row({
  to,
  icon,
  title,
  sub,
  end,
}: {
  to: string;
  icon: ReactNode;
  title: string;
  sub: string;
  end: ReactNode;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3.5 border-b border-line px-4 py-3 text-[13px] transition-colors last:border-b-0 hover:bg-sunk"
    >
      <span className="flex-none text-fg-3">{icon}</span>
      <span className="min-w-0 flex-1">
        <b className="block font-semibold text-fg">{title}</b>
        <span className="block truncate text-[12px] text-fg-3">{sub}</span>
      </span>
      {end}
      <ChevronRight aria-hidden="true" className="h-4 w-4 flex-none text-fg-3" />
    </Link>
  );
}

/** The desktop /settings page: the broker's health, then every section with its state. */
export function SettingsOverview() {
  const user = useAuthStore((s) => s.user);
  const { summary, states, brokerLoaded } = useSettingsSummary();
  const details = useSectionDetails();
  const name = displayName(user);

  return (
    <>
      <PageHead
        title="Settings"
        sub={[name, user?.email].filter(Boolean).join(' · ') || undefined}
      />
      <div className="grid gap-3">
        {brokerLoaded && <HealthCard summary={summary} />}
        <nav aria-label="Settings sections" className="panel overflow-hidden">
          {SECTIONS.map((s) => {
            const state = states[s.key];
            const value = details[s.key].value ?? state?.text;
            return (
              <Row
                key={s.key}
                to={sectionPath(s.key)}
                icon={<s.icon className="h-4 w-4" strokeWidth={1.7} />}
                title={s.label}
                sub={details[s.key].sub}
                end={
                  value ? (
                    <span
                      className={`hidden flex-none text-[12.5px] sm:inline ${state?.risk ? 'text-risk' : 'text-fg-3'}`}
                    >
                      {value}
                    </span>
                  ) : null
                }
              />
            );
          })}
        </nav>
      </div>
    </>
  );
}
