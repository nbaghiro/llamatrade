/**
 * SettingsPage - User settings with tabbed layout
 */

import { CreditCard, User } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useAuthStore } from '../store/auth';

type Tab = 'account' | 'billing';

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('account');
  const user = useAuthStore((state) => state.user);

  return (
    <div className="h-[calc(100vh-56px)] overflow-auto bg-gray-50 dark:bg-gray-950 bg-dotted-grid">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>
          <p className="mt-1 text-gray-500 dark:text-gray-400">
            Manage your account and preferences
          </p>
        </div>

        {/* Tabs */}
        <div className="mb-6 border-b border-gray-200 dark:border-gray-700">
          <nav className="-mb-px flex gap-6">
            <button
              onClick={() => setActiveTab('account')}
              className={`flex items-center gap-2 border-b-2 pb-3 text-sm font-medium transition-colors ${
                activeTab === 'account'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
            >
              <User className="h-4 w-4" />
              Account
            </button>
            <button
              onClick={() => setActiveTab('billing')}
              className={`flex items-center gap-2 border-b-2 pb-3 text-sm font-medium transition-colors ${
                activeTab === 'billing'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
            >
              <CreditCard className="h-4 w-4" />
              Plan & Billing
            </button>
          </nav>
        </div>

        {/* Tab Content */}
        {activeTab === 'account' && (
          <div className="space-y-6">
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
                Account Information
              </h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Email
                  </label>
                  <p className="mt-1 text-gray-900 dark:text-gray-100">{user?.email || '-'}</p>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
                Security
              </h2>
              <button className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800">
                Change Password
              </button>
            </div>
          </div>
        )}

        {activeTab === 'billing' && (
          <div className="space-y-6">
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
                Subscription
              </h2>
              <p className="mb-4 text-gray-500 dark:text-gray-400">
                View and manage your subscription, payment methods, and invoices.
              </p>
              <Link
                to="/billing"
                className="inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Manage Billing
              </Link>
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
                Payment Methods
              </h2>
              <p className="mb-4 text-gray-500 dark:text-gray-400">
                Add, remove, or update your payment methods.
              </p>
              <Link
                to="/billing/payment-methods"
                className="inline-block rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Manage Payment Methods
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
