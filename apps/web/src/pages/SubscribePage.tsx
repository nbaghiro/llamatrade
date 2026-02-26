/**
 * SubscribePage - Plan selection and subscription creation
 */

import { Elements } from '@stripe/react-stripe-js';
import { loadStripe } from '@stripe/stripe-js';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import CardForm from '../components/billing/CardForm';
import PlanCard from '../components/billing/PlanCard';
import { billingApi } from '../services/billing';
import { useBillingStore } from '../store/billing';
import type { BillingCycle, Plan } from '../types/billing';

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '');

export default function SubscribePage() {
  const navigate = useNavigate();
  const { plans, subscription, loading, error, fetchPlans, fetchSubscription, createSubscription, clearError } =
    useBillingStore();

  const [billingCycle, setBillingCycle] = useState<BillingCycle>('monthly');
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    fetchPlans();
    fetchSubscription();
  }, [fetchPlans, fetchSubscription]);

  const handleSelectPlan = async (plan: Plan) => {
    setSelectedPlan(plan);
    clearError();
    setLocalError(null);

    // Free plan doesn't need payment
    if (plan.tier === 'free') {
      setClientSecret(null);
      return;
    }

    // Create SetupIntent for card collection
    setSetupLoading(true);
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
    if (!selectedPlan) return;

    setSubmitLoading(true);
    setLocalError(null);
    try {
      await createSubscription(selectedPlan.id, paymentMethodId, billingCycle);
      navigate('/billing');
    } catch {
      setLocalError('Failed to create subscription. Please try again.');
    } finally {
      setSubmitLoading(false);
    }
  };

  const handleCardError = (errorMessage: string) => {
    setLocalError(errorMessage);
  };

  const handleFreePlan = async () => {
    if (!selectedPlan || selectedPlan.tier !== 'free') return;

    setSubmitLoading(true);
    setLocalError(null);
    try {
      await createSubscription(selectedPlan.id, '', billingCycle);
      navigate('/billing');
    } catch {
      setLocalError('Failed to create subscription. Please try again.');
    } finally {
      setSubmitLoading(false);
    }
  };

  const currentPlanId = subscription?.plan.id;
  const displayError = localError || error;
  const clearDisplayError = () => {
    setLocalError(null);
    clearError();
  };

  return (
    <div className="h-[calc(100vh-56px)] overflow-auto bg-gray-50 dark:bg-gray-950 bg-dotted-grid">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-8">
          <Link
            to="/billing"
            className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Billing
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Choose Your Plan
          </h1>
          <p className="mt-1 text-gray-500 dark:text-gray-400">
            Select a plan that works for your trading needs
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

        {/* Billing Cycle Toggle */}
        <div className="mb-8 flex justify-center">
          <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1 dark:border-gray-700 dark:bg-gray-900">
            <button
              onClick={() => setBillingCycle('monthly')}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                billingCycle === 'monthly'
                  ? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
                  : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBillingCycle('yearly')}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                billingCycle === 'yearly'
                  ? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
                  : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
              }`}
            >
              Yearly
              <span className="ml-1 text-xs text-green-600 dark:text-green-400">(Save 17%)</span>
            </button>
          </div>
        </div>

        {/* Plan Selection */}
        {loading && !plans.length ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-3">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                billingCycle={billingCycle}
                isCurrentPlan={plan.id === currentPlanId}
                onSelect={handleSelectPlan}
              />
            ))}
          </div>
        )}

        {/* Payment Form Modal */}
        {selectedPlan && selectedPlan.tier !== 'free' && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 dark:bg-gray-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
                Subscribe to {selectedPlan.name}
              </h2>
              <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">
                {selectedPlan.trial_days > 0
                  ? `Start your ${selectedPlan.trial_days}-day free trial. You won't be charged until the trial ends.`
                  : `You will be charged $${billingCycle === 'monthly' ? selectedPlan.price_monthly : selectedPlan.price_yearly}${billingCycle === 'yearly' ? '/year' : '/month'}.`}
              </p>

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
                    submitLabel={
                      selectedPlan.trial_days > 0
                        ? 'Start Free Trial'
                        : `Pay $${billingCycle === 'monthly' ? selectedPlan.price_monthly : selectedPlan.price_yearly}`
                    }
                    loading={submitLoading}
                  />
                </Elements>
              ) : (
                <div className="text-center py-4 text-gray-500">
                  Failed to initialize payment form. Please try again.
                </div>
              )}

              <button
                onClick={() => {
                  setSelectedPlan(null);
                  setClientSecret(null);
                }}
                className="mt-4 w-full text-center text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Free Plan Confirmation */}
        {selectedPlan && selectedPlan.tier === 'free' && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 dark:bg-gray-900">
              <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
                Switch to Free Plan
              </h2>
              <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">
                Are you sure you want to switch to the Free plan? Some features may be limited.
              </p>

              <div className="space-y-3">
                <button
                  onClick={handleFreePlan}
                  disabled={submitLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200"
                >
                  {submitLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  Confirm Switch
                </button>
                <button
                  onClick={() => setSelectedPlan(null)}
                  className="w-full text-center text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
