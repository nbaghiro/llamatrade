import {
  CLOSED_BETA,
  PLAN_TIER_BY_KEY,
  resolveCurrentTier,
} from '@llamatrade/core/billing/planTiers';
import { usagePeriod } from '@llamatrade/core/billing/usage';
import { useBillingStore, type BillingResource } from '@llamatrade/core/stores/billing';
import { CreditCard } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatRange } from '../../../components/billing/format';
import InvoiceTable from '../../../components/billing/InvoiceTable';
import PaymentMethodCard from '../../../components/billing/PaymentMethodCard';
import UsageMeter from '../../../components/billing/UsageMeter';
import { EmptyState, PanelError, Skeleton } from '../../../components/ui';
import { asSentence } from '../../../lib/format';
import { planCells } from '../model';
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

function PlanCard() {
  const subscription = useBillingStore((s) => s.subscription);
  const paymentMethods = useBillingStore((s) => s.paymentMethods);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);
  const { loaded, error } = usePanelState('subscription');

  if (!loaded) {
    return (
      <Panel title={<Skeleton className="h-3 w-16" />}>
        <PanelSkeleton />
      </Panel>
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
          body={
            CLOSED_BETA
              ? 'Testers are on Pro at no charge during the closed beta. Paper trading and backtests work without a plan.'
              : 'Choose a plan to raise your limits.'
          }
          actions={
            <Link to="/settings/plans" className="btn btn-secondary">
              See plans
            </Link>
          }
        />
      </section>
    );
  }

  const tier = PLAN_TIER_BY_KEY[resolveCurrentTier(subscription) ?? 'free'];
  const card = paymentMethods.find((p) => p.isDefault) ?? paymentMethods[0] ?? null;
  const cells = planCells(subscription, tier, card, CLOSED_BETA);

  return (
    <Panel
      title={<span className="text-[15px]">{subscription.plan?.name || tier.name}</span>}
      aside={
        CLOSED_BETA ? (
          <span className="badge badge-accent">Beta · no charge</span>
        ) : subscription.cancelAtPeriodEnd ? (
          <span className="badge badge-danger">Ending</span>
        ) : undefined
      }
      footer={
        <>
          <span className="text-fg-2">
            {tier.tagline}.{CLOSED_BETA ? " Live trading isn't available in the beta." : ''}
          </span>
          <Link to="/settings/plans" className="btn btn-secondary btn-sm">
            Compare plans
          </Link>
        </>
      }
    >
      <div className="grid grid-cols-3">
        {cells.map((c) => (
          <div
            key={c.label}
            className="grid min-w-0 content-start gap-0.5 border-r border-line px-3 py-3 text-[11px] last:border-r-0 sm:px-3.5 sm:text-[11.5px]"
          >
            <span className="text-[11px] font-medium text-fg-3">{c.label}</span>
            <span className="num truncate whitespace-nowrap text-[15px] tracking-[-0.01em] text-fg sm:text-[18px]">
              {c.value}
            </span>
            <span className="text-fg-3">{c.sub}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function UsagePanel() {
  const subscription = useBillingStore((s) => s.subscription);
  const usage = useBillingStore((s) => s.usageCounts);
  const period = usagePeriod(new Date());
  const { loaded: planLoaded, error: planError } = usePanelState('subscription');
  const tier = PLAN_TIER_BY_KEY[resolveCurrentTier(subscription) ?? 'free'];

  return (
    <Panel title="Usage this month" aside={formatRange(period.start, period.end)}>
      {usage === null || !planLoaded ? (
        <PanelSkeleton lines={4} />
      ) : planError ? (
        <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-2">
          Your limits show here once your plan loads.
        </p>
      ) : (
        <div className="grid gap-x-6 gap-y-4 px-3.5 py-3 sm:grid-cols-2">
          <UsageMeter label="Strategies" used={usage.strategies} limit={tier.limits.strategies} />
          <UsageMeter
            label="Backtests this month"
            used={usage.backtests}
            limit={tier.limits.backtestsPerMonth}
          />
          <UsageMeter
            label="Copilot messages"
            used={usage.copilotMessages}
            limit={tier.limits.copilotMessages}
          />
          <UsageMeter
            label="Live sessions"
            used={CLOSED_BETA ? 0 : usage.liveSessions}
            limit={tier.limits.liveSessions}
            note={CLOSED_BETA ? 'Not available in the beta' : undefined}
          />
        </div>
      )}
    </Panel>
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
        body={
          CLOSED_BETA
            ? "You won't need one until paid plans open."
            : 'Add a card to keep a paid plan.'
        }
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
    <div className="grid items-start gap-3 lg:grid-cols-[1.35fr_1fr]">
      <div className="grid min-w-0 gap-3">
        <PlanCard />
        <UsagePanel />
      </div>
      <div className="grid min-w-0 gap-3">
        <PaymentPanel />
        <InvoicesPanel />
      </div>
    </div>
  );
}
