/**
 * PaymentMethodsPage - Manage saved payment methods
 */

import { Elements } from '@stripe/react-stripe-js';
import { loadStripe } from '@stripe/stripe-js';
import { ArrowLeft, Loader2, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import CardForm from '../components/billing/CardForm';
import PaymentMethodCard from '../components/billing/PaymentMethodCard';
import { billingApi } from '../services/billing';
import { useBillingStore } from '../store/billing';

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '');

export default function PaymentMethodsPage() {
  const { paymentMethods, loading, error, fetchPaymentMethods, clearError } = useBillingStore();

  const [showAddForm, setShowAddForm] = useState(false);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    fetchPaymentMethods();
  }, [fetchPaymentMethods]);

  const handleAddCard = async () => {
    setShowAddForm(true);
    setSetupLoading(true);
    setLocalError(null);
    try {
      const response = await billingApi.createSetupIntent();
      setClientSecret(response.data.client_secret);
    } catch {
      setLocalError('Failed to create setup intent. Please try again.');
    } finally {
      setSetupLoading(false);
    }
  };

  const handleCardSuccess = async (paymentMethodId: string) => {
    setActionLoading(true);
    setLocalError(null);
    try {
      await billingApi.attachPaymentMethod({ payment_method_id: paymentMethodId });
      await fetchPaymentMethods();
      setShowAddForm(false);
      setClientSecret(null);
    } catch {
      setLocalError('Failed to attach payment method. Please try again.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCardError = (errorMessage: string) => {
    setLocalError(errorMessage);
  };

  const handleSetDefault = async (id: string) => {
    setActionLoading(true);
    setLocalError(null);
    try {
      await billingApi.setDefaultPaymentMethod(id);
      await fetchPaymentMethods();
    } catch {
      setLocalError('Failed to set default payment method. Please try again.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Are you sure you want to remove this payment method?')) {
      return;
    }

    setActionLoading(true);
    setLocalError(null);
    try {
      await billingApi.deletePaymentMethod(id);
      await fetchPaymentMethods();
    } catch {
      setLocalError('Failed to delete payment method. Please try again.');
    } finally {
      setActionLoading(false);
    }
  };

  const displayError = localError || error;
  const clearDisplayError = () => {
    setLocalError(null);
    clearError();
  };

  return (
    <div className="h-[calc(100vh-56px)] overflow-auto bg-gray-50 dark:bg-gray-950 bg-dotted-grid">
      <div className="mx-auto max-w-2xl px-6 py-8">
        <div className="mb-8">
          <Link
            to="/billing"
            className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Billing
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Payment Methods
          </h1>
          <p className="mt-1 text-gray-500 dark:text-gray-400">
            Manage your saved payment methods
          </p>
        </div>

        {displayError && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 dark:bg-red-900/20">
            <div className="flex items-center justify-between">
              <p className="text-sm text-red-600 dark:text-red-400">{displayError}</p>
              <button
                onClick={clearDisplayError}
                className="text-sm text-red-600 hover:text-red-700 dark:text-red-400"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Payment Methods List */}
        {loading && !paymentMethods.length ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          </div>
        ) : (
          <div className="space-y-4">
            {paymentMethods.map((pm) => (
              <PaymentMethodCard
                key={pm.id}
                paymentMethod={pm}
                onSetDefault={handleSetDefault}
                onDelete={handleDelete}
                loading={actionLoading}
              />
            ))}

            {paymentMethods.length === 0 && !showAddForm && (
              <div className="rounded-lg border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-900">
                <p className="text-gray-500 dark:text-gray-400">
                  No payment methods saved yet.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Add Card Button */}
        {!showAddForm && (
          <button
            onClick={handleAddCard}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-300 bg-white py-4 text-gray-500 hover:border-gray-400 hover:text-gray-600 dark:border-gray-600 dark:bg-gray-900 dark:hover:border-gray-500 dark:hover:text-gray-400"
          >
            <Plus className="h-5 w-5" />
            Add a new card
          </button>
        )}

        {/* Add Card Form */}
        {showAddForm && (
          <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
              Add New Card
            </h2>

            {setupLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
              </div>
            ) : clientSecret ? (
              <Elements stripe={stripePromise}>
                <CardForm
                  clientSecret={clientSecret}
                  onSuccess={handleCardSuccess}
                  onError={handleCardError}
                  submitLabel="Save Card"
                  loading={actionLoading}
                />
              </Elements>
            ) : (
              <div className="text-center py-4 text-gray-500">
                Failed to initialize payment form. Please try again.
              </div>
            )}

            <button
              onClick={() => {
                setShowAddForm(false);
                setClientSecret(null);
              }}
              className="mt-4 w-full text-center text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
