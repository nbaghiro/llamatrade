import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { ArrowRight, CreditCard, LogOut, Moon, Settings, type LucideIcon } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import { useAuthStore } from '../../store/auth';
import { useThemeStore } from '../../store/theme';
import { Avatar } from '../common/Avatar';
import { ModeBadge } from '../ui/ModeBadge';
import { Popover } from '../ui/Popover';

import { connectionRows, type ConnectionRow } from './connections';
import { useSessionRows } from './useSessionRows';

const MODE_WORD = { system: 'System', light: 'Light', dark: 'Dark' } as const;

function Connection({ row }: { row: ConnectionRow }) {
  const ran =
    row.sessions === 0
      ? 'No sessions running'
      : `${row.sessions} session${row.sessions === 1 ? '' : 's'}${row.value === null ? '' : ` · ${formatMoney(row.value)}`}`;
  return (
    <div className="rounded-[10px] border border-line px-3 py-2.5">
      <div className="flex items-center gap-2">
        <ModeBadge mode={row.mode} size="sm" />
        <span className="font-mono text-[12.5px] text-fg">{row.masked || row.name}</span>
        <span
          className={`ml-auto inline-flex items-center gap-1.5 text-[12px] ${row.connected ? 'text-fg-2' : 'text-risk'}`}
        >
          <i
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${row.connected ? 'bg-accent' : 'bg-risk'}`}
          />
          {row.connected ? 'Connected' : 'Not active'}
        </span>
      </div>
      <div className="mt-1 text-[11.5px] text-fg-3">{ran}</div>
    </div>
  );
}

function Item({
  to,
  icon: Icon,
  label,
  aside,
  onClick,
}: {
  to?: string;
  icon: LucideIcon;
  label: string;
  aside?: string;
  onClick: () => void;
}) {
  const cls =
    'flex w-full items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-left text-[13px] text-fg-2 hover:bg-sunk hover:text-fg focus-visible:bg-sunk';
  const body = (
    <>
      <Icon aria-hidden="true" className="h-4 w-4 flex-none" />
      <span className="text-fg">{label}</span>
      {aside && <span className="ml-auto text-[12px] text-fg-3">{aside}</span>}
    </>
  );
  return to ? (
    <Link role="menuitem" to={to} onClick={onClick} className={cls}>
      {body}
    </Link>
  ) : (
    <button role="menuitem" type="button" onClick={onClick} className={cls}>
      {body}
    </button>
  );
}

/** The account menu leads with the Alpaca connections, then plan, settings and sign-out (account2 A). */
export function AccountMenu() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const credentials = useBrokerStore((s) => s.credentials);
  const brokerLoaded = useBrokerStore((s) => s.loaded);
  const brokerLoading = useBrokerStore((s) => s.loading);
  const fetchCredentials = useBrokerStore((s) => s.fetch);
  const sessionRows = useSessionRows();
  const themeMode = useThemeStore((s) => s.mode);

  useEffect(() => {
    fetchSubscription().catch(() => undefined);
  }, [fetchSubscription]);
  useEffect(() => {
    if (!brokerLoaded && !brokerLoading) fetchCredentials().catch(() => undefined);
  }, [brokerLoaded, brokerLoading, fetchCredentials]);

  const rows = useMemo(
    () =>
      connectionRows(
        credentials,
        sessionRows.map((r) => ({
          mode: r.session.mode,
          isActive: r.session.isActive,
          equity: r.figures.equity,
        }))
      ),
    [credentials, sessionRows]
  );
  const name = [user?.firstName, user?.lastName].filter(Boolean).join(' ');
  const plan = subscription?.plan?.name;
  const avatar = (size: number) => (
    <Avatar
      avatarUrl={user?.avatarUrl}
      firstName={user?.firstName}
      lastName={user?.lastName}
      email={user?.email}
      size={size}
    />
  );

  return (
    <Popover
      label="Account"
      role="menu"
      width={340}
      trigger={(props) => (
        <button type="button" {...props} aria-label="Account" className="ml-0.5 rounded-full">
          {avatar(30)}
        </button>
      )}
    >
      {(close) => (
        <>
          <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
            {avatar(32)}
            <div className="min-w-0">
              {name && <b className="block truncate text-[13.5px] font-semibold">{name}</b>}
              <div className="truncate text-xs text-fg-3">{user?.email}</div>
            </div>
          </div>

          <div className="border-b border-line px-3 pb-3 pt-2.5">
            <div className="kicker mb-2 px-1 uppercase tracking-[0.06em]">Alpaca accounts</div>
            {rows.length ? (
              <div className="grid gap-2">
                {rows.map((r) => (
                  <Connection key={r.id} row={r} />
                ))}
              </div>
            ) : (
              <Link
                to="/connect/alpaca"
                onClick={close}
                className="flex items-center gap-2 rounded-[10px] border border-dashed border-line-strong px-3 py-2.5 text-[12.5px] text-fg-2 hover:text-fg"
              >
                {brokerLoaded ? 'No Alpaca account connected yet.' : 'Loading accounts…'}
                {brokerLoaded && (
                  <span className="ml-auto inline-flex items-center gap-1 font-medium text-fg">
                    Connect <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
                  </span>
                )}
              </Link>
            )}
          </div>

          <div className="grid p-1.5">
            <Item
              to="/settings/plan"
              icon={CreditCard}
              label={plan ? `${plan} plan` : 'Plan and usage'}
              aside="Billing"
              onClick={close}
            />
            <Item to="/settings/profile" icon={Settings} label="Settings" onClick={close} />
            <Item
              to="/settings/appearance"
              icon={Moon}
              label="Appearance"
              aside={MODE_WORD[themeMode]}
              onClick={close}
            />
            <Item
              icon={LogOut}
              label="Sign out"
              onClick={() => {
                close();
                logout();
                navigate('/');
              }}
            />
          </div>
        </>
      )}
    </Popover>
  );
}
