/**
 * SubscriptionStatus component - displays current subscription details
 */


import type { Subscription } from '@llamatrade/core/proto/billing_pb';
import { BillingInterval, SubscriptionStatus as SubStatus } from '@llamatrade/core/proto/billing_pb';
import type { Timestamp } from '@llamatrade/core/proto/common_pb';
import { AlertTriangle, Calendar, Clock, RefreshCw } from 'lucide-react';

interface SubscriptionStatusProps {
  subscription: Subscription;
  onCancel: () => void;
  onReactivate: () => void;
  loading?: boolean;
}

function formatDate(timestamp: Timestamp | undefined): string {
  if (!timestamp) return '-';
  const date = new Date(Number(timestamp.seconds) * 1000);
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function getDaysUntil(timestamp: Timestamp | undefined): number {
  if (!timestamp) return 0;
  const date = new Date(Number(timestamp.seconds) * 1000);
  const now = new Date();
  const diffTime = date.getTime() - now.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

function getStatusString(status: SubStatus): string {
  switch (status) {
    case SubStatus.ACTIVE:
      return 'active';
    case SubStatus.PAST_DUE:
      return 'past_due';
    case SubStatus.CANCELED:
      return 'cancelled';
    case SubStatus.TRIALING:
      return 'trialing';
    case SubStatus.PAUSED:
      return 'paused';
    default:
      return 'unknown';
  }
}

export default function SubscriptionStatus({
  subscription,
  onCancel,
  onReactivate,
  loading = false,
}: SubscriptionStatusProps) {
  const statusStr = getStatusString(subscription.status);
  const isTrialing = subscription.status === SubStatus.TRIALING;
  const isCancelling = subscription.cancelAtPeriodEnd;
  const isPastDue = subscription.status === SubStatus.PAST_DUE;

  const trialDaysRemaining = subscription.trialEnd
    ? getDaysUntil(subscription.trialEnd)
    : 0;

  const planName = subscription.plan?.name ?? 'Unknown Plan';
  const monthlyPrice = subscription.plan?.monthlyPrice?.amount ?? '0';
  const isYearly = subscription.interval === BillingInterval.YEARLY;

  return (
    <div className="border-2 border-ink bg-paper p-6 dark:border-gray-700 dark:bg-gray-900">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-display uppercase tracking-tight text-ink">
              {planName} Plan
            </h3>
            <StatusBadge status={statusStr} cancelling={isCancelling} />
          </div>

          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            ${monthlyPrice}/month
            {isYearly && ' (billed annually)'}
          </p>
        </div>

        <div className="text-right">
          <p className="text-[11px] font-mono uppercase tracking-wide text-ink/50">
            {isCancelling ? 'Cancels on' : 'Next billing date'}
          </p>
          <p className="font-medium text-ink dark:text-gray-100">
            {formatDate(subscription.currentPeriodEnd)}
          </p>
        </div>
      </div>

      {isTrialing && subscription.trialEnd && (
        <div className="mt-4 border-2 border-ink bg-orange-50 p-4 dark:bg-amber-900/20">
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-orange-600 dark:text-amber-400" />
            <span className="font-medium text-orange-700 dark:text-amber-400">
              Trial Period Active
            </span>
          </div>
          <p className="mt-1 text-sm text-orange-700 dark:text-amber-400">
            Your trial ends on {formatDate(subscription.trialEnd)}.
            {trialDaysRemaining > 0
              ? ` ${trialDaysRemaining} day${trialDaysRemaining === 1 ? '' : 's'} remaining.`
              : ' Ends today.'}
          </p>
        </div>
      )}

      {isPastDue && (
        <div className="mt-4 border-2 border-red-500 bg-red-50 p-4 dark:bg-red-900/20">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
            <span className="font-medium text-red-700 dark:text-red-400">Payment Failed</span>
          </div>
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
            Your last payment failed. Please update your payment method to continue service.
          </p>
        </div>
      )}

      {isCancelling && (
        <div className="mt-4 border-2 border-ink bg-bone p-4 dark:bg-gray-800">
          <div className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-ink/60 dark:text-gray-400" />
            <span className="font-medium text-ink dark:text-gray-300">
              Subscription Cancelled
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Your subscription will end on {formatDate(subscription.currentPeriodEnd)}. You can
            reactivate anytime before then.
          </p>
        </div>
      )}

      <div className="mt-6 flex items-center gap-3">
        {isCancelling ? (
          <button
            onClick={onReactivate}
            disabled={loading}
            className="btn btn-primary"
          >
            <RefreshCw className="h-4 w-4" />
            Reactivate Subscription
          </button>
        ) : (
          <button
            onClick={onCancel}
            disabled={loading}
            className="btn btn-secondary"
          >
            Cancel Subscription
          </button>
        )}
      </div>
    </div>
  );
}

function StatusBadge({
  status,
  cancelling,
}: {
  status: string;
  cancelling: boolean;
}) {
  if (cancelling) {
    return (
      <span className="badge badge-gray">
        Cancelling
      </span>
    );
  }

  switch (status) {
    case 'active':
      return (
        <span className="badge badge-success">
          Active
        </span>
      );
    case 'trialing':
      return (
        <span className="badge bg-orange-500 text-ink">
          Trial
        </span>
      );
    case 'past_due':
      return (
        <span className="badge badge-danger">
          Past Due
        </span>
      );
    case 'cancelled':
      return (
        <span className="badge badge-gray">
          Cancelled
        </span>
      );
    default:
      return null;
  }
}
