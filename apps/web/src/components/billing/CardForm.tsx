/**
 * CardForm component - Stripe CardElement wrapper with custom styling
 */

import { CardElement, useElements, useStripe } from '@stripe/react-stripe-js';
import type { StripeCardElementChangeEvent } from '@stripe/stripe-js';
import { AlertCircle, CreditCard, Loader2 } from 'lucide-react';
import { useState } from 'react';

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
  submitLabel = 'Add Card',
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
        setCardError(error.message || 'An error occurred');
        onError(error.message || 'An error occurred');
      } else if (setupIntent && setupIntent.payment_method) {
        const paymentMethodId =
          typeof setupIntent.payment_method === 'string'
            ? setupIntent.payment_method
            : setupIntent.payment_method.id;
        onSuccess(paymentMethodId);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred';
      setCardError(message);
      onError(message);
    } finally {
      setProcessing(false);
    }
  };

  const isDisabled = !stripe || !cardComplete || processing || loading;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Card Details
        </label>
        <div className="relative">
          <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
            <CreditCard className="h-5 w-5 text-gray-400" />
          </div>
          <div className="pl-10 pr-3 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus-within:ring-2 focus-within:ring-indigo-500 focus-within:border-indigo-500">
            <CardElement
              options={{
                style: {
                  base: {
                    fontSize: '16px',
                    color: '#1f2937',
                    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                    '::placeholder': {
                      color: '#9ca3af',
                    },
                  },
                  invalid: {
                    color: '#ef4444',
                  },
                },
                hidePostalCode: true,
              }}
              onChange={handleCardChange}
            />
          </div>
        </div>
      </div>

      {cardError && (
        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
          <AlertCircle className="h-4 w-4" />
          <span>{cardError}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={isDisabled}
        className={`w-full flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
          isDisabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-gray-800 dark:text-gray-500'
            : 'bg-indigo-600 text-white hover:bg-indigo-700'
        }`}
      >
        {(processing || loading) && <Loader2 className="h-4 w-4 animate-spin" />}
        {processing ? 'Processing...' : submitLabel}
      </button>

      <p className="text-xs text-center text-gray-500 dark:text-gray-400">
        Your card details are securely processed by Stripe.
      </p>
    </form>
  );
}
