import { CardElement, useElements, useStripe } from '@stripe/react-stripe-js';
import type { StripeCardElementChangeEvent } from '@stripe/stripe-js';
import { AlertCircle, CreditCard, Loader2 } from 'lucide-react';
import { useState } from 'react';

/** Stripe's card iframe can't read CSS variables, so the token values are resolved here. */
function tokenColor(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const channels = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
  return channels ? `rgb(${channels.split(/\s+/).join(', ')})` : fallback;
}

interface CardFormProps {
  clientSecret: string;
  onSuccess: (paymentMethodId: string) => void;
  onError: (error: string) => void;
  submitLabel?: string;
  loading?: boolean;
}

export default function CardForm({
  clientSecret,
  onSuccess,
  onError,
  submitLabel = 'Save card',
  loading = false,
}: CardFormProps) {
  const stripe = useStripe();
  const elements = useElements();
  const [cardError, setCardError] = useState<string | null>(null);
  const [cardComplete, setCardComplete] = useState(false);
  const [processing, setProcessing] = useState(false);

  const handleCardChange = (event: StripeCardElementChangeEvent) => {
    setCardComplete(event.complete);
    if (event.error) {
      setCardError(event.error.message);
    } else {
      setCardError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      return;
    }

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      return;
    }

    setProcessing(true);
    setCardError(null);

    try {
      const { error, setupIntent } = await stripe.confirmCardSetup(clientSecret, {
        payment_method: {
          card: cardElement,
        },
      });

      if (error) {
        setCardError(error.message || "The card couldn't be saved. Please try again.");
        onError(error.message || "The card couldn't be saved. Please try again.");
      } else if (setupIntent && setupIntent.payment_method) {
        const paymentMethodId =
          typeof setupIntent.payment_method === 'string'
            ? setupIntent.payment_method
            : setupIntent.payment_method.id;
        onSuccess(paymentMethodId);
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "The card couldn't be saved. Please try again.";
      setCardError(message);
      onError(message);
    } finally {
      setProcessing(false);
    }
  };

  const isDisabled = !stripe || !cardComplete || processing || loading;

  return (
    <form onSubmit={handleSubmit} className="grid gap-3">
      <div>
        <span className="label">Card details</span>
        <div className="flex items-center gap-2.5 rounded-[6px] border border-line-strong bg-panel px-3 py-2.5 focus-within:border-accent">
          <CreditCard className="h-4 w-4 flex-none text-fg-3" />
          <div className="min-w-0 flex-1">
            <CardElement
              options={{
                style: {
                  base: {
                    fontSize: '14px',
                    color: tokenColor('fg', '#888888'),
                    fontFamily: 'Geist, system-ui, sans-serif',
                    '::placeholder': { color: tokenColor('fg-3', '#888888') },
                  },
                  invalid: { color: tokenColor('risk', '#c78a00') },
                },
                hidePostalCode: true,
              }}
              onChange={handleCardChange}
            />
          </div>
        </div>
      </div>

      {cardError && (
        <p role="alert" className="m-0 flex items-center gap-2 text-xs text-risk">
          <AlertCircle className="h-3.5 w-3.5" />
          {cardError}
        </p>
      )}

      <button type="submit" disabled={isDisabled} className="btn btn-primary w-full">
        {(processing || loading) && <Loader2 className="h-4 w-4 motion-safe:animate-spin" />}
        {processing ? 'Saving…' : submitLabel}
      </button>

      <p className="m-0 text-center text-xs text-fg-3">
        Card details go straight to Stripe and never reach LlamaTrade.
      </p>
    </form>
  );
}
