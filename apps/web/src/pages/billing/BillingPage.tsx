/**
 * BillingPage (V1 "Plan-Comparison") — subscription overview, plan comparison,
 * invoice history and payment method. Everything user-specific is real billing
 * API data; the plan tiers/feature rows come from product config.
 */

import { ArrowUpRight, Download, Plus, Zap } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { formatDate, formatUsd, moneyToNumber } from '../../components/billing/format';
import InkPaymentCard from '../../components/billing/InkPaymentCard';
import InvoiceTable from '../../components/billing/InvoiceTable';
import PlanComparison from '../../components/billing/PlanComparison';
import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '../../data/planTiers';
import { BillingInterval, SubscriptionStatus } from '../../generated/proto/billing_pb';
import { useAuthStore } from '../../store/auth';
import { useBillingStore } from '../../store/billing';

function statusMeta(status: SubscriptionStatus, cancelling: boolean): { label: string; dot: string } {
  if (cancelling) return { label: 'Cancelling', dot: 'bg-orange-500' };
  switch (status) {
    case SubscriptionStatus.ACTIVE:
      return { label: 'Active', dot: 'bg-green-500' };
    case SubscriptionStatus.PAST_DUE:
      return { label: 'Past Due', dot: 'bg-red-500' };
    case SubscriptionStatus.TRIALING:
      return { label: 'Trial', dot: 'bg-orange-500' };
    case SubscriptionStatus.PAUSED:
      return { label: 'Paused', dot: 'bg-ink/40' };
    case SubscriptionStatus.CANCELED:
      return { label: 'Canceled', dot: 'bg-ink/40' };
    default:
      return { label: 'Inactive', dot: 'bg-ink/40' };
  }
}

function holderNameOf(user: { firstName?: string; lastName?: string; email?: string } | null): string {
  if (!user) return '';
  const full = `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim();
  if (full) return full;
  if (user.email) return user.email.split('@')[0].replace(/[._-]/g, ' ');
  return '';
}

export default function BillingPage() {
  const navigate = useNavigate();
  const {
    subscription,
    invoices,
    paymentMethods,
    error,
    loading,
    fetchSubscription,
    fetchInvoices,
    fetchPaymentMethods,
    cancelSubscription,
    resumeSubscription,
    clearError,
  } = useBillingStore();
  const user = useAuthStore((s) => s.user);

  const [yearly, setYearly] = useState(false);

  useEffect(() => {
    fetchSubscription();
    fetchInvoices();
    fetchPaymentMethods();
  }, [fetchSubscription, fetchInvoices, fetchPaymentMethods]);

  const currentTier = resolveCurrentTier(subscription);
  const planName =
    subscription?.plan?.name || (currentTier ? PLAN_TIER_BY_KEY[currentTier].name : 'Free');
  const cancelling = subscription?.cancelAtPeriodEnd ?? false;
  const status = statusMeta(subscription?.status ?? SubscriptionStatus.UNSPECIFIED, cancelling);
  const monthlyAmount =
    moneyToNumber(subscription?.currentPrice) || moneyToNumber(subscription?.plan?.monthlyPrice);
  const intervalLabel =
    subscription?.interval === BillingInterval.YEARLY ? 'Yearly billing' : 'Monthly billing';
  const nextInvoiceDate = formatDate(subscription?.currentPeriodEnd);
  const renewDate = formatDate(subscription?.currentPeriodEnd).replace(/, \d{4}$/, '');

  const defaultPm = useMemo(
    () => paymentMethods.find((pm) => pm.isDefault) ?? paymentMethods[0] ?? null,
    [paymentMethods],
  );
  const holderName = holderNameOf(user);
  const pmSummary = defaultPm
    ? `${(defaultPm.cardBrand || 'Card').replace(/^\w/, (c) => c.toUpperCase())} •••• ${defaultPm.cardLast4}`
    : 'No card on file';

  const downloadable = invoices.filter((i) => i.pdfUrl);
  const handleDownloadAll = () => {
    downloadable.forEach((i) => window.open(i.pdfUrl, '_blank', 'noopener,noreferrer'));
  };

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

  return (
    <div className="min-h-[calc(100vh-56px)] bg-bone bg-grid">
      <div className="mx-auto max-w-[1760px] px-6 py-6 lg:px-8">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink/45">
              Settings / Billing
            </p>
            <h1 className="mt-1 font-display text-[34px] uppercase leading-[0.92] tracking-[0.01em]">
              Plan &amp; Billing
            </h1>
            <p className="mt-1.5 text-sm text-ink/55">
              Manage your subscription, payment method &amp; invoices
            </p>
          </div>
          {subscription && (
            <span className="inline-flex items-center gap-2 border-2 border-ink bg-paper px-3 py-1.5 shadow-[3px_3px_0_rgb(var(--lt-ink))]">
              <span className={`h-2 w-2 ${status.dot}`} />
              <span className="font-mono text-[11px] font-bold uppercase tracking-wide text-ink">
                {planName} · {status.label}
              </span>
            </span>
          )}
        </div>

        {error && (
          <div className="mb-6 flex items-center justify-between border-2 border-ink bg-orange-500 px-4 py-2">
            <p className="font-mono text-[11px] font-bold uppercase tracking-wide text-ink">{error}</p>
            <button
              onClick={clearError}
              className="font-mono text-[11px] font-bold uppercase tracking-wide text-ink/70 hover:text-ink"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Active plan bar — ink surface, so ORANGE offset shadow */}
        {subscription && (
          <div className="mb-8 border-2 border-ink bg-ink text-bone shadow-[6px_6px_0_rgb(var(--lt-orange-500))]">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-4 px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center border-2 border-bone/20 bg-orange-500">
                  <Zap className="h-5 w-5 text-ink" />
                </div>
                <div>
                  <p className="font-display text-lg uppercase leading-none tracking-tight text-bone">
                    {planName} Plan
                  </p>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-bone/55">
                    {status.label} · {intervalLabel}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                <BarCell label="Next Invoice" value={nextInvoiceDate} />
                <BarCell label="Amount" value={formatUsd(monthlyAmount)} />
                <BarCell label="Payment" value={pmSummary} />
              </div>

              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={() => navigate('/billing/subscribe')}
                  className="bg-orange-500 px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-bone"
                >
                  Manage Plan
                </button>
                {cancelling ? (
                  <button
                    onClick={handleReactivate}
                    disabled={loading}
                    className="border-2 border-bone/40 px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-bone transition-colors hover:bg-bone hover:text-ink disabled:opacity-50"
                  >
                    Reactivate
                  </button>
                ) : (
                  <button
                    onClick={handleCancel}
                    disabled={loading}
                    className="border-2 border-bone/40 px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-bone transition-colors hover:bg-bone hover:text-ink disabled:opacity-50"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Choose your plan */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl uppercase tracking-tight">Choose Your Plan</h2>
          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-[10px] uppercase tracking-wide text-ink/45 sm:inline">
              Prices in USD · Switch anytime
            </span>
            <div className="inline-flex border-2 border-ink bg-paper p-0.5">
              <button
                onClick={() => setYearly(false)}
                className={`px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wide transition-colors ${
                  !yearly ? 'bg-ink text-bone' : 'text-ink/55 hover:text-ink'
                }`}
              >
                Monthly
              </button>
              <button
                onClick={() => setYearly(true)}
                className={`px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wide transition-colors ${
                  yearly ? 'bg-ink text-bone' : 'text-ink/55 hover:text-ink'
                }`}
              >
                Yearly <span className="text-green-600">-17%</span>
              </button>
            </div>
          </div>
        </div>

        <div className="mb-8">
          <PlanComparison
            currentTier={currentTier}
            yearly={yearly}
            renewDate={renewDate}
            onChoose={() => navigate('/billing/subscribe')}
          />
        </div>

        {/* Invoice history + payment method */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.7fr_1fr]">
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-ink/60">
                Invoice History
              </h2>
              <button
                onClick={handleDownloadAll}
                disabled={downloadable.length === 0}
                className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-wide text-orange-600 transition-colors hover:text-ink disabled:cursor-not-allowed disabled:text-ink/25"
              >
                <Download className="h-3.5 w-3.5" />
                Download All
              </button>
            </div>
            <InvoiceTable invoices={invoices} />
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.1em] text-ink/60">
                Payment Method
              </h2>
              <button
                onClick={() => navigate('/billing/payment-methods')}
                className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-wide text-orange-600 transition-colors hover:text-ink"
              >
                <Plus className="h-3.5 w-3.5" />
                Add Card
              </button>
            </div>
            <InkPaymentCard paymentMethod={defaultPm} holderName={holderName} />
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                onClick={() => navigate('/billing/payment-methods')}
                className="flex items-center justify-center gap-1 border-2 border-ink bg-orange-500 py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-orange-500"
              >
                Update Card
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => navigate('/billing/payment-methods')}
                className="border-2 border-ink bg-bone py-2 font-mono text-[11px] font-bold uppercase tracking-wide text-ink transition-colors hover:bg-ink hover:text-bone"
              >
                Billing Info
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function BarCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l border-bone/15 pl-6">
      <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-bone/50">{label}</p>
      <p className="mt-1 font-mono text-[13px] font-bold text-bone tabular-nums">{value}</p>
    </div>
  );
}
