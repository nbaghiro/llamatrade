/**
 * BillingPage - Subscription overview and management
 */

import { CreditCard, FileText, Settings } from 'lucide-react';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';

import SubscriptionStatus from '../components/billing/SubscriptionStatus';
import { useBillingStore } from '../store/billing';

export default function BillingPage() {
  const {
    subscription,
    invoices,
    loading,
    error,
    fetchSubscription,
    fetchInvoices,
    cancelSubscription,
    resumeSubscription,
    clearError,
  } = useBillingStore();

  useEffect(() => {
    fetchSubscription();
    fetchInvoices();
  }, [fetchSubscription, fetchInvoices]);

  const handleCancel = async () => {
    if (window.confirm('Are you sure you want to cancel your subscription? You will still have access until the end of your billing period.')) {
      try {
        await cancelSubscription(true);
      } catch {
        // Error is handled by store
      }
    }
  };

  const handleReactivate = async () => {
    try {
      await resumeSubscription();
    } catch {
      // Error is handled by store
    }
  };

  return (
    <div className="h-[calc(100vh-56px)] overflow-auto bg-gray-50 dark:bg-gray-950 bg-dotted-grid">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Billing & Subscription
          </h1>
          <p className="mt-1 text-gray-500 dark:text-gray-400">
            Manage your subscription, payment methods, and view invoices
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 dark:bg-red-900/20">
            <div className="flex items-center justify-between">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
              <button
                onClick={clearError}
                className="text-sm text-red-600 hover:text-red-700 dark:text-red-400"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Subscription Status */}
        <section className="mb-8">
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Current Subscription
          </h2>
          {subscription ? (
            <SubscriptionStatus
              subscription={subscription}
              onCancel={handleCancel}
              onReactivate={handleReactivate}
              loading={loading}
            />
          ) : (
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
              <p className="text-gray-500 dark:text-gray-400">
                You don&apos;t have an active subscription.
              </p>
              <Link
                to="/billing/subscribe"
                className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Choose a Plan
              </Link>
            </div>
          )}
        </section>

        {/* Quick Actions */}
        <section className="mb-8">
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Quick Actions
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <Link
              to="/billing/subscribe"
              className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-4 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800"
            >
              <div className="rounded-lg bg-indigo-100 p-2 dark:bg-indigo-900/30">
                <Settings className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100">Change Plan</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Upgrade or downgrade
                </p>
              </div>
            </Link>

            <Link
              to="/billing/payment-methods"
              className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-4 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800"
            >
              <div className="rounded-lg bg-green-100 p-2 dark:bg-green-900/30">
                <CreditCard className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100">Payment Methods</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Manage your cards</p>
              </div>
            </Link>

            <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
              <div className="rounded-lg bg-amber-100 p-2 dark:bg-amber-900/30">
                <FileText className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              </div>
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100">Invoices</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {invoices.length} invoice{invoices.length !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Recent Invoices */}
        {invoices.length > 0 && (
          <section>
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
              Recent Invoices
            </h2>
            <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-gray-400">
                      Date
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-gray-400">
                      Amount
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-gray-400">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-gray-500 dark:text-gray-400">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.slice(0, 5).map((invoice) => (
                    <tr
                      key={invoice.id}
                      className="border-b border-gray-200 last:border-0 dark:border-gray-700"
                    >
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                        {invoice.periodStart ? new Date(Number(invoice.periodStart.seconds) * 1000).toLocaleDateString() : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                        ${invoice.amount?.amount ?? '0.00'} {(invoice.amount?.currency ?? 'USD').toUpperCase()}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            invoice.status === 'paid'
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                          }`}
                        >
                          {invoice.status.charAt(0).toUpperCase() + invoice.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {invoice.pdfUrl && (
                          <a
                            href={invoice.pdfUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
                          >
                            Download
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
