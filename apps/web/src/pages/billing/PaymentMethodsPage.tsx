import { CLOSED_BETA } from '@llamatrade/core/billing/planTiers';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { Elements } from '@stripe/react-stripe-js';
import { loadStripe, type Stripe } from '@stripe/stripe-js';
import { AlertTriangle, ChevronLeft, CreditCard, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import CardForm from '../../components/billing/CardForm';
import { cardSummary } from '../../components/billing/format';
import PaymentMethodCard from '../../components/billing/PaymentMethodCard';
import { Dialog, EmptyState, PanelError, SkeletonRows } from '../../components/ui';
import { billingClient } from '../../services/grpc-client';
import { getTenantContext } from '../../store/auth';
import { Panel } from '../settings/parts';

const STRIPE_KEY = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY ?? '';
let stripePromise: Promise<Stripe | null> | null = null;

/** Loads Stripe.js on first use, so other pages never fetch it. */
function getStripe(): Promise<Stripe | null> | null {
  if (!STRIPE_KEY) return null;
  stripePromise ??= loadStripe(STRIPE_KEY);
  return stripePromise;
}

export default function PaymentMethodsPage() {
  const paymentMethods = useBillingStore((s) => s.paymentMethods);
  const loaded = useBillingStore((s) => s.loaded.paymentMethods ?? false);
  const loadError = useBillingStore((s) => s.errors.paymentMethods);
  const fetchPaymentMethods = useBillingStore((s) => s.fetchPaymentMethods);
  const [removeId, setRemoveId] = useState<string | null>(null);

  const [showAddForm, setShowAddForm] = useState(false);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    fetchPaymentMethods().catch(() => undefined);
  }, [fetchPaymentMethods]);

  const handleAddCard = async () => {
    setShowAddForm(true);
    setSetupLoading(true);
    setLocalError(null);
    try {
      const response = await billingClient.createSetupIntent({ context: getTenantContext() });
      setClientSecret(response.clientSecret || null);
    } catch {
      setLocalError("The card form couldn't be opened. Please try again.");
    } finally {
      setSetupLoading(false);
    }
  };

  const handleCardSuccess = async (setupIntentId: string) => {
    setActionLoading(true);
    setLocalError(null);
    try {
      await billingClient.addPaymentMethod({
        context: getTenantContext(),
        setupIntentId,
        setAsDefault: paymentMethods.length === 0,
      });
      await fetchPaymentMethods();
      setShowAddForm(false);
      setClientSecret(null);
    } catch {
      setLocalError("The card couldn't be saved. Please try again.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCardError = (errorMessage: string) => {
    setLocalError(errorMessage);
  };

  const handleDelete = async (id: string) => {
    setActionLoading(true);
    setLocalError(null);
    try {
      await billingClient.removePaymentMethod({
        context: getTenantContext(),
        paymentMethodId: id,
      });
      await fetchPaymentMethods();
      setRemoveId(null);
    } catch {
      setLocalError("The card couldn't be removed. Please try again.");
    } finally {
      setActionLoading(false);
    }
  };

  const removing = paymentMethods.find((pm) => pm.id === removeId) ?? null;
  const closeForm = () => {
    setShowAddForm(false);
    setClientSecret(null);
  };

  return (
    <div className="page max-w-[720px]">
      <Link
        to="/settings/plan"
        className="mb-2 inline-flex items-center gap-0.5 text-[13px] text-accent hover:underline"
      >
        <ChevronLeft className="h-4 w-4" />
        Plan and usage
      </Link>
      <h1 className="m-0 text-[21px] leading-tight">Payment methods</h1>
      <p className="mb-4 mt-[3px] text-[12.5px] text-fg-3">
        {CLOSED_BETA
          ? "You won't need a card until paid plans open after the beta."
          : 'The default card pays for your plan.'}
      </p>

      {localError && (
        <div
          role="alert"
          className="mb-3 flex items-center gap-2.5 rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2.5 text-[12.5px] text-fg-2"
        >
          <AlertTriangle className="h-4 w-4 flex-none text-risk" />
          <span className="min-w-0 flex-1">{localError}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setLocalError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid gap-3">
        <Panel title="Saved cards">
          {!loaded ? (
            <SkeletonRows rows={2} cols={2} />
          ) : loadError ? (
            <PanelError
              title="Saved cards couldn't be loaded"
              onRetry={() => {
                fetchPaymentMethods().catch(() => undefined);
              }}
            />
          ) : paymentMethods.length === 0 ? (
            <EmptyState
              icon={CreditCard}
              title="No card on file"
              body="Cards you add appear here. Stripe keeps the card details."
            />
          ) : (
            <div className="divide-y divide-line">
              {paymentMethods.map((pm) => (
                <PaymentMethodCard
                  key={pm.id}
                  paymentMethod={pm}
                  onDelete={setRemoveId}
                  loading={actionLoading}
                />
              ))}
            </div>
          )}
        </Panel>

        {showAddForm ? (
          <Panel
            title="Add a card"
            aside={
              <button type="button" className="text-fg-3 hover:text-fg" onClick={closeForm}>
                Cancel
              </button>
            }
          >
            <div className="px-3.5 py-3">
              {setupLoading ? (
                <SkeletonRows rows={2} cols={1} />
              ) : clientSecret ? (
                <Elements stripe={getStripe()}>
                  <CardForm
                    clientSecret={clientSecret}
                    onSuccess={(id) => {
                      handleCardSuccess(id).catch(() => undefined);
                    }}
                    onError={handleCardError}
                    submitLabel="Save card"
                    loading={actionLoading}
                  />
                </Elements>
              ) : (
                <p className="m-0 text-[12.5px] text-fg-2">
                  The card form couldn&apos;t be opened. Close this and try again.
                </p>
              )}
            </div>
          </Panel>
        ) : STRIPE_KEY ? (
          <button
            type="button"
            className="btn btn-secondary justify-self-start"
            onClick={() => {
              handleAddCard().catch(() => undefined);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            Add a card
          </button>
        ) : (
          <p className="m-0 text-[12.5px] text-fg-3">
            Adding a card isn&apos;t set up on this server yet.
          </p>
        )}
      </div>

      <Dialog
        open={removing !== null}
        onClose={() => setRemoveId(null)}
        title="Remove this card?"
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setRemoveId(null)}>
              Keep it
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={actionLoading}
              onClick={() => {
                if (removing) handleDelete(removing.id).catch(() => undefined);
              }}
            >
              Remove
            </button>
          </>
        }
      >
        <p className="m-0 text-[13px] text-fg-2">
          {removing ? cardSummary(removing.cardBrand, removing.cardLast4) : 'This card'} will be
          removed from your account.
        </p>
      </Dialog>
    </div>
  );
}
