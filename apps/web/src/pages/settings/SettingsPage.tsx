/**
 * SettingsPage (V2 "Account-Style") — account settings with a full tab bar. The
 * Billing tab is the fully wired surface (real subscription, payment method,
 * usage meters and invoices); Profile shows the real account identity; the
 * remaining tabs are honest placeholders rather than non-functional controls.
 */

import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '@llamatrade/core/billing/planTiers';
import { SubscriptionStatus } from '@llamatrade/core/proto/billing_pb';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import {
  ArrowUpRight,
  Bell,
  CreditCard,
  KeyRound,
  Lock,
  Plus,
  Shield,
  User,
  Warehouse,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  billingCycleProgress,
  formatDate,
  formatDayMonth,
  formatMonthYear,
  formatUsd,
  moneyToNumber,
} from '../../components/billing/format';
import InkPaymentCard from '../../components/billing/InkPaymentCard';
import InvoiceTable from '../../components/billing/InvoiceTable';
import UsageMeter from '../../components/billing/UsageMeter';
import { useAuthStore } from '../../store/auth';


type Tab = 'profile' | 'broker' | 'billing' | 'notifications' | 'security';

const TABS: { key: Tab; label: string; icon: LucideIcon }[] = [
  { key: 'profile', label: 'Profile', icon: User },
  { key: 'broker', label: 'Broker Keys', icon: KeyRound },
  { key: 'billing', label: 'Billing', icon: CreditCard },
  { key: 'notifications', label: 'Notifications', icon: Bell },
  { key: 'security', label: 'Security', icon: Shield },
];

function holderNameOf(user: { firstName?: string; lastName?: string; email?: string } | null): string {
  if (!user) return '';
  const full = `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim();
  if (full) return full;
  if (user.email) return user.email.split('@')[0].replace(/[._-]/g, ' ');
  return '';
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('billing');
  const user = useAuthStore((s) => s.user);

  const tenantShort = user?.tenantId ? user.tenantId.replace(/-/g, '').slice(0, 4) : '—';

  return (
    <div className="min-h-[calc(100vh-56px)] bg-bone bg-grid">
      <div className="mx-auto max-w-[1760px] px-6 py-6 lg:px-8">
        {/* Header */}
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink/45">
              Account
            </p>
            <h1 className="mt-1 font-display text-[34px] uppercase leading-[0.92] tracking-[0.01em]">
              Settings
            </h1>
          </div>
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50">
            Signed in as <span className="font-bold text-ink">{user?.email ?? '—'}</span> · Tenant #
            {tenantShort}
          </p>
        </div>

        {/* Tab bar */}
        <div className="mb-6 flex flex-wrap gap-1 border-b-2 border-ink">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`inline-flex items-center gap-2 px-4 py-2.5 font-mono text-[11px] font-bold uppercase tracking-wide transition-colors ${
                  active ? 'bg-ink text-bone' : 'text-ink/55 hover:bg-ink/5 hover:text-ink'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {activeTab === 'billing' && <BillingTab user={user} />}
        {activeTab === 'profile' && <ProfileTab user={user} tenantShort={tenantShort} />}
        {activeTab === 'broker' && <BrokerTab />}
        {activeTab === 'notifications' && (
          <Placeholder
            title="Notifications"
            body="Email and in-app alert preferences are coming soon."
          />
        )}
        {activeTab === 'security' && (
          <Placeholder
            title="Security"
            body="Password changes, sessions and two-factor authentication are coming soon."
          />
        )}
      </div>
    </div>
  );
}

// Billing tab

function BillingTab({ user }: { user: ReturnType<typeof useAuthStore.getState>['user'] }) {
  const navigate = useNavigate();
  const {
    subscription,
    paymentMethods,
    invoices,
    usageCounts,
    error,
    loading,
    fetchSubscription,
    fetchPaymentMethods,
    fetchInvoices,
    fetchUsageCounts,
    cancelSubscription,
    resumeSubscription,
    clearError,
  } = useBillingStore();

  useEffect(() => {
    fetchSubscription();
    fetchPaymentMethods();
    fetchInvoices();
    fetchUsageCounts();
  }, [fetchSubscription, fetchPaymentMethods, fetchInvoices, fetchUsageCounts]);

  const currentTier = resolveCurrentTier(subscription);
  const tier = PLAN_TIER_BY_KEY[currentTier ?? 'free'];
  const planName = subscription?.plan?.name || tier.name;
  const cancelling = subscription?.cancelAtPeriodEnd ?? false;
  const isActive = subscription?.status === SubscriptionStatus.ACTIVE && !cancelling;
  const monthlyAmount =
    moneyToNumber(subscription?.currentPrice) || moneyToNumber(subscription?.plan?.monthlyPrice);
  const memberSince = formatMonthYear(subscription?.createdAt ?? subscription?.currentPeriodStart);

  const defaultPm = useMemo(
    () => paymentMethods.find((pm) => pm.isDefault) ?? paymentMethods[0] ?? null,
    [paymentMethods],
  );
  const holderName = holderNameOf(user);
  const pmSummary = defaultPm
    ? `${(defaultPm.cardBrand || 'Card').replace(/^\w/, (c) => c.toUpperCase())} •••• ${defaultPm.cardLast4}`
    : 'No card on file';

  const cycle = billingCycleProgress(subscription?.currentPeriodStart, subscription?.currentPeriodEnd);
  const usage = usageCounts ?? { strategies: 0, backtests: 0, liveSessions: 0, copilotMessages: 0 };

  const handleCancel = async () => {
    if (
      window.confirm(
        'Cancel your subscription? You keep access until the end of the current billing period.',
      )
    ) {
      try {
        await cancelSubscription(true);
      } catch {
        // surfaced via store error
      }
    }
  };

  const handleReactivate = async () => {
    try {
      await resumeSubscription();
    } catch {
      // surfaced via store error
    }
  };

  if (!subscription) {
    return (
      <div className="border-2 border-ink bg-paper p-8 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
        <h2 className="font-display text-xl uppercase tracking-tight">No active subscription</h2>
        <p className="mt-1.5 text-sm text-ink/55">Choose a plan to unlock live trading and Copilot.</p>
        <button
          onClick={() => navigate('/billing/subscribe')}
          className="mt-4 border-2 border-ink bg-orange-500 px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-orange-500"
        >
          Choose a Plan
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="flex items-center justify-between border-2 border-ink bg-orange-500 px-4 py-2">
          <p className="font-mono text-[11px] font-bold uppercase tracking-wide text-ink">{error}</p>
          <button
            onClick={clearError}
            className="font-mono text-[11px] font-bold uppercase tracking-wide text-ink/70 hover:text-ink"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.7fr_1fr]">
        {/* Current subscription */}
        <section className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
          <div className="flex items-center justify-between">
            <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-ink/60">
              Current Subscription
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-wide text-ink/45">
              Member since {memberSince}
            </span>
          </div>

          <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center border-2 border-ink bg-orange-500">
                <Zap className="h-5 w-5 text-ink" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-display text-2xl uppercase leading-none tracking-tight">
                    {planName}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 border border-ink px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${
                      isActive ? 'bg-green-600 text-bone' : 'bg-bone text-ink'
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 ${isActive ? 'bg-bone' : 'bg-orange-500'}`} />
                    {cancelling ? 'Cancelling' : isActive ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-ink/50">
                  {tier.tagline} · Monthly billing
                </p>
              </div>
            </div>
            <div className="text-right">
              <p className="font-display text-3xl leading-none">{formatUsd(monthlyAmount)}</p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-ink/50">per month</p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 border-2 border-ink sm:grid-cols-3">
            <SubCell label="Next Bill" value={formatDate(subscription.currentPeriodEnd)} border />
            <SubCell label="Amount Due" value={formatUsd(monthlyAmount)} border />
            <SubCell label="Paid With" value={pmSummary} />
          </div>

          {cycle && (
            <div className="mt-5">
              <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-wide text-ink/50">
                <span>
                  Billing cycle · {formatDayMonth(subscription.currentPeriodStart)} –{' '}
                  {formatDayMonth(subscription.currentPeriodEnd)}
                </span>
                <span className="text-ink/70">
                  Day {cycle.elapsedDays} of {cycle.totalDays}
                </span>
              </div>
              <div className="mt-2 h-2.5 w-full border border-ink bg-bone">
                <div className="h-full bg-ink" style={{ width: `${cycle.fraction * 100}%` }} />
              </div>
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <button
              onClick={() => navigate('/billing/subscribe')}
              className="inline-flex items-center gap-1 border-2 border-ink bg-orange-500 px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-orange-500"
            >
              Change Plan
              <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => navigate('/billing/payment-methods')}
              className="border-2 border-ink bg-bone px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-bone"
            >
              Update Payment
            </button>
            {cancelling ? (
              <button
                onClick={handleReactivate}
                disabled={loading}
                className="ml-auto font-mono text-[11px] font-bold uppercase tracking-wide text-green-600 hover:text-ink disabled:opacity-50"
              >
                Reactivate Subscription
              </button>
            ) : (
              <button
                onClick={handleCancel}
                disabled={loading}
                className="ml-auto font-mono text-[11px] font-bold uppercase tracking-wide text-ink/45 underline-offset-2 hover:text-red-600 hover:underline disabled:opacity-50"
              >
                Cancel Subscription
              </button>
            )}
          </div>
        </section>

        {/* Payment method */}
        <section className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-ink/60">
              Payment Method
            </h2>
            <button
              onClick={() => navigate('/billing/payment-methods')}
              className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-wide text-orange-600 transition-colors hover:text-ink"
            >
              <Plus className="h-3.5 w-3.5" />
              Add
            </button>
          </div>

          <InkPaymentCard paymentMethod={defaultPm} holderName={holderName} />

          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              onClick={() => navigate('/billing/payment-methods')}
              className="border-2 border-ink bg-orange-500 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-orange-500"
            >
              Change
            </button>
            <button
              onClick={() => navigate('/billing/payment-methods')}
              className="border-2 border-ink bg-bone py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-bone"
            >
              Remove
            </button>
          </div>

          <dl className="mt-5 space-y-2.5">
            <InfoRow label="Billing email" value={user?.email ?? '—'} />
            <InfoRow label="Country" value="—" />
            <InfoRow label="Tax ID" value="—" />
          </dl>
        </section>
      </div>

      {/* Usage meters */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <UsageMeter label="Strategies" used={usage.strategies} limit={tier.limits.strategies} />
        <UsageMeter label="Backtests" used={usage.backtests} limit={tier.limits.backtestsPerMonth} />
        <UsageMeter label="Live Sessions" used={usage.liveSessions} limit={tier.limits.liveSessions} />
        <UsageMeter
          label="Copilot Msgs"
          used={usage.copilotMessages}
          limit={tier.limits.copilotMessages}
        />
      </div>

      {/* Invoices */}
      <section>
        <h2 className="mb-3 font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-ink/60">
          Invoices &amp; Receipts
        </h2>
        <InvoiceTable invoices={invoices} showDescription />
      </section>

      {/* Change plan footer */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t-2 border-ink pt-5">
        <p className="font-mono text-[11px] uppercase tracking-wide text-ink/55">
          You&apos;re on {planName} · Upgrade or downgrade anytime
        </p>
        <button
          onClick={() => navigate('/billing/subscribe')}
          className="border-2 border-ink bg-ink px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-bone transition-colors hover:bg-ink/85"
        >
          Change Plan
        </button>
      </div>
    </div>
  );
}

// Broker keys tab

type Env = 'paper' | 'live';

function BrokerTab() {
  const navigate = useNavigate();
  const { credentials, connecting, error, fetch, connect, remove, clearError } = useBrokerStore();
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const canLive = (subscription?.plan?.maxLiveSessions ?? 0) > 0;

  const [env, setEnv] = useState<Env>('paper');
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    fetch();
    fetchSubscription();
  }, [fetch, fetchSubscription]);

  useEffect(() => {
    if (!canLive && env === 'live') setEnv('paper');
  }, [canLive, env]);

  const submit = async () => {
    clearError();
    setLocalError('');
    if (!apiKey.trim() || !apiSecret.trim()) {
      setLocalError('Enter both your API key ID and secret key.');
      return;
    }
    const ok = await connect({
      name,
      apiKey: apiKey.trim(),
      apiSecret: apiSecret.trim(),
      isPaper: env === 'paper',
    });
    if (ok) {
      setName('');
      setApiKey('');
      setApiSecret('');
    }
  };

  const handleRemove = (id: string, label: string) => {
    if (window.confirm(`Disconnect “${label}”? Live sessions using it will stop.`)) {
      void remove(id);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.6fr_1fr]">
      {/* Connect */}
      <section className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
        <div className="border-2 border-ink bg-ink p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center border-2 border-orange-500">
              <Warehouse className="h-5 w-5 text-orange-500" />
            </div>
            <div>
              <h2 className="font-display text-xl uppercase leading-none tracking-tight text-bone">
                Link Alpaca
              </h2>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-bone/55">
                Bring your own broker keys
              </p>
            </div>
          </div>
          <p className="mt-3 font-mono text-[10px] uppercase leading-relaxed tracking-wide text-bone/50">
            The exact strategy you backtest is what trades. Connect your Alpaca keys to go live.
          </p>
        </div>

        {/* Environment */}
        <div className="mt-5">
          <span className="label">Environment</span>
          <div className="flex">
            {(['paper', 'live'] as Env[]).map((e) => {
              const active = env === e;
              const disabled = e === 'live' && !canLive;
              return (
                <button
                  key={e}
                  type="button"
                  disabled={disabled}
                  onClick={() => setEnv(e)}
                  className={`-ml-[2px] flex-1 border-2 border-ink px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide transition-colors first:ml-0 ${
                    active ? 'bg-ink text-bone' : 'bg-paper text-ink hover:bg-ink/5'
                  } ${disabled ? 'cursor-not-allowed opacity-40' : ''}`}
                >
                  {e}
                </button>
              );
            })}
          </div>
          {!canLive && (
            <button
              onClick={() => navigate('/billing/subscribe')}
              className="mt-2 inline-flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-wide text-ink/45 transition-colors hover:text-orange-600"
            >
              <Lock className="h-3 w-3" />
              Live trading requires a Pro plan · View plans →
            </button>
          )}
        </div>

        {/* Keys */}
        <div className="mt-4 space-y-4">
          <div>
            <label className="label" htmlFor="alp-name">
              Label (optional)
            </label>
            <input
              id="alp-name"
              className="input"
              value={name}
              onChange={(ev) => setName(ev.target.value)}
              placeholder="My Alpaca account"
            />
          </div>
          <div>
            <label className="label" htmlFor="alp-key">
              API Key ID
            </label>
            <input
              id="alp-key"
              className="input font-mono"
              value={apiKey}
              onChange={(ev) => setApiKey(ev.target.value)}
              placeholder="PK…"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
            />
          </div>
          <div>
            <label className="label" htmlFor="alp-secret">
              Secret Key
            </label>
            <input
              id="alp-secret"
              type="password"
              className="input font-mono"
              value={apiSecret}
              onChange={(ev) => setApiSecret(ev.target.value)}
              placeholder="••••••••••••••••"
              autoComplete="off"
            />
          </div>
        </div>

        {/* Security note */}
        <div className="mt-4 flex items-start gap-2 border-2 border-green-600 bg-green-100 px-3 py-2.5">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-green-700" />
          <p className="font-mono text-[10px] leading-relaxed text-green-700">
            Keys are validated with Alpaca, encrypted at rest, and sent only over TLS — never stored
            in plaintext or in the browser.
          </p>
        </div>

        {(localError || error) && (
          <div className="mt-4 border-2 border-red-500 bg-red-50 px-3 py-2">
            <p className="font-mono text-[10px] text-red-600">{localError || error}</p>
          </div>
        )}

        <button
          onClick={submit}
          disabled={connecting}
          className="mt-5 inline-flex w-full items-center justify-center gap-1.5 border-2 border-ink bg-orange-500 py-3 font-mono text-[12px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-orange-500 disabled:opacity-60"
        >
          {connecting ? 'Verifying…' : 'Connect & Verify →'}
        </button>
      </section>

      {/* Connected accounts */}
      <section className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
        <h2 className="mb-4 font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-ink/60">
          Connected Accounts
        </h2>
        {credentials.length ? (
          <div className="space-y-2.5">
            {credentials.map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-3 border-2 border-ink bg-bone px-3 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[12px] font-bold text-ink">
                    {c.name || 'Alpaca account'}
                  </p>
                  <p className="font-mono text-[10px] text-ink/50">{c.apiKeyPrefix}••••</p>
                </div>
                <span
                  className={`border border-ink px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${
                    c.isPaper ? 'bg-bone text-ink' : 'bg-green-600 text-bone'
                  }`}
                >
                  {c.isPaper ? 'Paper' : 'Live'}
                </span>
                <button
                  onClick={() => handleRemove(c.id, c.name || 'Alpaca account')}
                  className="text-ink/40 transition-colors hover:text-red-600"
                  aria-label="Remove credentials"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/40">
            No broker keys linked yet.
          </p>
        )}
      </section>
    </div>
  );
}

// Other tabs

function ProfileTab({
  user,
  tenantShort,
}: {
  user: ReturnType<typeof useAuthStore.getState>['user'];
  tenantShort: string;
}) {
  const name = holderNameOf(user);
  return (
    <div className="max-w-2xl border-2 border-ink bg-paper p-6 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <h2 className="mb-5 font-display text-xl uppercase tracking-tight">Account Information</h2>
      <dl className="space-y-4">
        <InfoRow label="Name" value={name || '—'} />
        <InfoRow label="Email" value={user?.email ?? '—'} />
        <InfoRow label="Tenant" value={`#${tenantShort}`} />
        <InfoRow label="Roles" value={user?.roles?.length ? user.roles.join(', ') : 'Member'} />
      </dl>
    </div>
  );
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <div className="max-w-2xl border-2 border-dashed border-ink/40 bg-paper p-8">
      <h2 className="font-display text-xl uppercase tracking-tight">{title}</h2>
      <p className="mt-2 text-sm text-ink/55">{body}</p>
      <span className="mt-4 inline-block border border-ink bg-bone px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-ink/60">
        Coming soon
      </span>
    </div>
  );
}

// Small shared pieces

function SubCell({ label, value, border = false }: { label: string; value: string; border?: boolean }) {
  return (
    <div className={`px-4 py-3 ${border ? 'border-b-2 border-ink sm:border-b-0 sm:border-r-2' : ''}`}>
      <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink/45">{label}</p>
      <p className="mt-1 font-mono text-[13px] font-bold text-ink tabular-nums">{value}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="font-mono text-[10px] uppercase tracking-wide text-ink/50">{label}</dt>
      <dd className="font-mono text-[12px] text-ink">{value}</dd>
    </div>
  );
}
