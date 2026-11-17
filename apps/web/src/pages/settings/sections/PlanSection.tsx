import { PLAN_TIER_BY_KEY, resolveCurrentTier } from '@llamatrade/core/billing/planTiers';
import { meterState, usagePeriod } from '@llamatrade/core/billing/usage';
import { useBillingStore, type BillingResource } from '@llamatrade/core/stores/billing';
import { CreditCard, Receipt } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import InvoiceTable from '../../../components/billing/InvoiceTable';
import PaymentMethodCard from '../../../components/billing/PaymentMethodCard';
import { EmptyState, PanelError, Skeleton } from '../../../components/ui';
import { asSentence } from '../../../lib/format';
import { monthForecast } from '../health';
import { planLine } from '../model';
import { Panel } from '../parts';

function PanelSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="grid gap-3 px-3.5 py-4" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={`h-2.5 ${i % 2 ? 'w-1/2' : 'w-3/4'}`} />
      ))}
    </div>
  );
}

function usePanelState(resource: BillingResource) {
  const loaded = useBillingStore((s) => s.loaded[resource] ?? false);
  const error = useBillingStore((s) => s.errors[resource]);
  return { loaded, error };
}

function PlanLine() {
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const { loaded, error } = usePanelState('subscription');

  if (!loaded) {
    return (
      <div className="panel-rim px-5 py-4" aria-busy="true">
        <Skeleton className="h-4 w-48" />
      </div>
    );
  }
  if (error) {
    return (
      <section className="panel">
        <PanelError
          title="Your plan couldn't be loaded"
          cause={asSentence(error)}
          unaffected="Strategies and sessions aren't affected."
          onRetry={() => {
            fetchSubscription().catch(() => undefined);
          }}
        />
      </section>
    );
  }
  if (!subscription) {
    return (
      <section className="panel">
        <EmptyState
          icon={CreditCard}
          title="No plan on this account yet"
          body="Choose a plan to raise your limits. Paper trading and backtests work without one."
          actions={
            <Link to="/settings/plans" className="btn btn-secondary">
              See plans
            </Link>
          }
        />
      </section>
    );
  }

  const line = planLine(subscription, PLAN_TIER_BY_KEY[resolveCurrentTier(subscription) ?? 'free']);
  return (
    <section
      aria-label="Your plan"
      className="panel-rim flex flex-wrap items-center gap-x-3.5 gap-y-1.5 px-5 py-4"
    >
      <h2 className="m-0 text-[20px] font-semibold tracking-[-0.015em]">{line.name}</h2>
      {line.badge && (
        <span className={`badge ${line.ending ? 'badge-danger' : 'badge-accent'}`}>
          {line.badge}
        </span>
      )}
      <span className="min-w-0 flex-1 basis-[260px] text-[13px] text-fg-2">{line.note}</span>
      <span className="num text-[26px] tracking-[-0.02em]">{line.amount}</span>
    </section>
  );
}

function ForecastMeter({
  used,
  limit,
  forecast,
}: {
  used: number;
  limit: number;
  forecast: number | null;
}) {
  const pct = (v: number) => `${Math.round(Math.max(0, Math.min(1, v / limit)) * 1000) / 10}%`;
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={limit}
      aria-valuenow={used}
      className="relative h-2 overflow-hidden rounded-[4px] bg-sunk"
    >
      {forecast !== null && forecast > used && (
        <i
          aria-hidden="true"
          className="absolute inset-y-0 left-0 rounded-[4px] border border-dashed border-accent/70 bg-accent-soft"
          style={{ width: pct(forecast) }}
        />
      )}
      <i
        aria-hidden="true"
        className={`absolute inset-y-0 left-0 rounded-[4px] ${used >= limit ? 'bg-risk' : 'bg-accent-fill'}`}
        style={{ width: pct(used) }}
      />
    </div>
  );
}

function UsageRow({
  label,
  sub,
  used,
  limit,
  forecast = null,
}: {
  label: string;
  sub: string;
  used: number;
  limit: number;
  forecast?: number | null;
}) {
  const m = meterState(used, limit);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-5 gap-y-1.5 border-b border-line px-4 py-3 last:border-b-0 md:grid-cols-[200px_minmax(0,1fr)_110px]">
      <div className="min-w-0">
        <b className="block text-[13px] font-semibold">{label}</b>
        <span className={`block text-[11.5px] ${m.atLimit ? 'text-risk' : 'text-fg-3'}`}>
          {m.atLimit ? 'At the limit' : sub}
        </span>
      </div>
      <div className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto">
        {m.unlimited || limit === 0 ? (
          <span className="text-[12px] text-fg-3">{m.note}</span>
        ) : (
          <ForecastMeter used={used} limit={limit} forecast={forecast} />
        )}
      </div>
      <span className="num col-start-2 row-start-1 text-right text-[13px] md:col-start-auto md:row-start-auto">
        {used.toLocaleString('en-US')}
        {!m.unlimited && limit > 0 && (
          <span className="text-fg-3"> of {limit.toLocaleString('en-US')}</span>
        )}
      </span>
    </div>
  );
}

function UsagePanel() {
  const subscription = useBillingStore((s) => s.subscription);
  const usage = useBillingStore((s) => s.usageCounts);
  const { loaded: planLoaded, error: planError } = usePanelState('subscription');
  const tier = PLAN_TIER_BY_KEY[resolveCurrentTier(subscription) ?? 'free'];
  const now = new Date();
  const end = usagePeriod(now).end;
  const endLabel = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const forecastSub = (used: number, limit: number) => {
    const f = monthForecast(used, now);
    if (f === null || limit <= 0) return { forecast: null, sub: `Resets after ${endLabel}` };
    return { forecast: f, sub: `About ${f.toLocaleString('en-US')} by ${endLabel} at this pace` };
  };

  if (usage === null || !planLoaded) {
    return (
      <section className="panel" aria-label="Usage this month">
        <PanelSkeleton lines={4} />
      </section>
    );
  }
  if (planError) {
    return (
      <p className="panel m-0 px-4 py-4 text-[12.5px] text-fg-2">
        Your limits show here once your plan loads.
      </p>
    );
  }
  const bt = forecastSub(usage.backtests, tier.limits.backtestsPerMonth);
  const cp = forecastSub(usage.copilotMessages, tier.limits.copilotMessages);
  return (
    <div className="grid gap-2">
      <section className="panel" aria-label="Usage this month">
        <UsageRow
          label="Strategies"
          sub="Not a monthly count"
          used={usage.strategies}
          limit={tier.limits.strategies}
        />
        <UsageRow
          label="Backtests"
          sub={bt.sub}
          forecast={bt.forecast}
          used={usage.backtests}
          limit={tier.limits.backtestsPerMonth}
        />
        <UsageRow
          label="Copilot messages"
          sub={cp.sub}
          forecast={cp.forecast}
          used={usage.copilotMessages}
          limit={tier.limits.copilotMessages}
        />
        <UsageRow
          label="Live sessions"
          sub="Paper sessions don't count"
          used={usage.liveSessions}
          limit={tier.limits.liveSessions}
        />
      </section>
      <div className="flex flex-wrap gap-4 text-[11.5px] text-fg-3">
        <span className="inline-flex items-center gap-1.5">
          <i aria-hidden="true" className="h-2 w-3.5 rounded-[2px] bg-accent-fill" />
          Used so far
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i
            aria-hidden="true"
            className="h-2 w-3.5 rounded-[2px] border border-dashed border-accent/70 bg-accent-soft"
          />
          Forecast at this month&apos;s pace
        </span>
      </div>
    </div>
  );
}

function PaymentPanel() {
  const paymentMethods = useBillingStore((s) => s.paymentMethods);
  const fetchPaymentMethods = useBillingStore((s) => s.fetchPaymentMethods);
  const { loaded, error } = usePanelState('paymentMethods');
  const card = paymentMethods.find((p) => p.isDefault) ?? paymentMethods[0] ?? null;

  let body: ReactNode;
  if (!loaded) body = <PanelSkeleton lines={2} />;
  else if (error)
    body = (
      <PanelError
        title="Payment details couldn't be loaded"
        onRetry={() => {
          fetchPaymentMethods().catch(() => undefined);
        }}
      />
    );
  else if (!card)
    body = (
      <EmptyState
        className="!py-[26px]"
        icon={CreditCard}
        title="No card on file"
        body="Add a card to keep a paid plan."
      />
    );
  else body = <PaymentMethodCard paymentMethod={card} />;

  return (
    <Panel
      title="Payment method"
      aside={
        <Link to="/billing/payment-methods" className="text-accent hover:underline">
          {card ? 'Manage' : 'Add a card'}
        </Link>
      }
    >
      {body}
    </Panel>
  );
}

function InvoicesPanel() {
  const invoices = useBillingStore((s) => s.invoices);
  const fetchInvoices = useBillingStore((s) => s.fetchInvoices);
  const { loaded, error } = usePanelState('invoices');
  return (
    <Panel title="Invoices">
      {!loaded ? (
        <PanelSkeleton lines={2} />
      ) : error ? (
        <PanelError
          title="Invoices couldn't be loaded"
          onRetry={() => {
            fetchInvoices().catch(() => undefined);
          }}
        />
      ) : invoices.length === 0 ? (
        <EmptyState
          className="!py-[26px]"
          icon={Receipt}
          title="No invoices yet"
          body="You haven't been charged."
        />
      ) : (
        <InvoiceTable invoices={invoices} />
      )}
    </Panel>
  );
}

export function PlanSection() {
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const fetchPaymentMethods = useBillingStore((s) => s.fetchPaymentMethods);
  const fetchInvoices = useBillingStore((s) => s.fetchInvoices);
  const fetchUsageCounts = useBillingStore((s) => s.fetchUsageCounts);

  useEffect(() => {
    fetchSubscription().catch(() => undefined);
    fetchPaymentMethods().catch(() => undefined);
    fetchInvoices().catch(() => undefined);
    fetchUsageCounts().catch(() => undefined);
  }, [fetchSubscription, fetchPaymentMethods, fetchInvoices, fetchUsageCounts]);

  return (
    <div className="grid gap-4">
      <PlanLine />
      <UsagePanel />
      <div className="grid items-start gap-3 md:grid-cols-2">
        <PaymentPanel />
        <InvoicesPanel />
      </div>
    </div>
  );
}
