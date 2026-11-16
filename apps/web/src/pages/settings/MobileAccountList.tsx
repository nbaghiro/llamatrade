import {
  CLOSED_BETA,
  PLAN_TIER_BY_KEY,
  resolveCurrentTier,
} from '@llamatrade/core/billing/planTiers';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { ChevronRight } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Avatar } from '../../components/common/Avatar';
import { StatusMark } from '../../components/ui';
import { useAuthStore } from '../../store/auth';
import { useResolvedTheme } from '../../store/theme';

import { displayName } from './model';
import { MobileRow } from './parts';
import { SECTIONS, sectionPath, type SectionKey } from './sections';

/** The Account tab on a phone: who's signed in and a row per section. */
export function MobileAccountList() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const credentials = useBrokerStore((s) => s.credentials);
  const fetchBroker = useBrokerStore((s) => s.fetch);
  const unread = useNotificationsStore((s) => s.unreadCount);
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const theme = useResolvedTheme();

  useEffect(() => {
    fetchBroker().catch(() => undefined);
    fetchSubscription().catch(() => undefined);
  }, [fetchBroker, fetchSubscription]);

  const name = displayName(user);
  const cred = credentials.find((c) => c.isActive) ?? null;
  const tier = resolveCurrentTier(subscription);
  const surface = theme.mode === 'dark' ? theme.theme : theme.light;

  const end: Record<SectionKey, ReactNode> = {
    profile: null,
    broker: cred ? (
      <StatusMark state="running" label={cred.isPaper ? 'Alpaca paper' : 'Alpaca live'} />
    ) : (
      <span className="text-fg-3">Not connected</span>
    ),
    notifications: unread > 0 ? <span className="text-fg-3">{unread} unread</span> : null,
    appearance: (
      <span className="text-fg-3 capitalize">
        {theme.mode} · {surface}
      </span>
    ),
    plan: tier ? (
      <span className="text-fg-3">
        {PLAN_TIER_BY_KEY[tier].name}
        {CLOSED_BETA ? ' · beta' : ''}
      </span>
    ) : null,
  };

  return (
    <div className="flex min-h-[calc(100dvh-140px)] flex-col gap-3 px-4 py-5">
      <h1 className="m-0 text-[27px] leading-tight">Account</h1>
      <div className="flex items-center gap-3 rounded-[13px] border border-line bg-panel px-4 py-3.5">
        <Avatar
          avatarUrl={user?.avatarUrl}
          firstName={user?.firstName}
          lastName={user?.lastName}
          email={user?.email}
          size={44}
        />
        <span className="min-w-0">
          {name && <b className="block truncate text-[16px] font-semibold">{name}</b>}
          <span className="block truncate text-[13.5px] text-fg-3">{user?.email}</span>
        </span>
      </div>

      <nav aria-label="Account" className="rounded-[13px] border border-line bg-panel px-4 py-0.5">
        {SECTIONS.map((s) => (
          <Link key={s.key} to={sectionPath(s.key)} className="block">
            <MobileRow
              end={
                <>
                  {end[s.key]}
                  <ChevronRight className="h-4 w-4 text-fg-3" />
                </>
              }
            >
              {s.label}
            </MobileRow>
          </Link>
        ))}
        <Link to="/notifications" className="block">
          <MobileRow end={<ChevronRight className="h-4 w-4 text-fg-3" />}>
            All notifications
          </MobileRow>
        </Link>
      </nav>

      <button
        type="button"
        className="mt-auto h-[50px] rounded-[12px] border border-line-strong bg-panel text-[15.5px] font-semibold text-fg"
        onClick={() => {
          logout();
          navigate('/');
        }}
      >
        Sign out
      </button>
    </div>
  );
}
