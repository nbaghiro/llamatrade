/**
 * PaymentMethodCard component - displays a saved payment method
 */

import { CreditCard, MoreVertical, Star, Trash2 } from 'lucide-react';
import { useState } from 'react';

import type { PaymentMethod } from '../../types/billing';

interface PaymentMethodCardProps {
  paymentMethod: PaymentMethod;
  onSetDefault: (id: string) => void;
  onDelete: (id: string) => void;
  loading?: boolean;
}

const CARD_BRAND_COLORS: Record<string, string> = {
  visa: 'text-blue-600',
  mastercard: 'text-orange-500',
  amex: 'text-blue-500',
  discover: 'text-orange-600',
  default: 'text-gray-500',
};

export default function PaymentMethodCard({
  paymentMethod,
  onSetDefault,
  onDelete,
  loading = false,
}: PaymentMethodCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  const brandColor = CARD_BRAND_COLORS[paymentMethod.card_brand || 'default'];
  const brandName = paymentMethod.card_brand
    ? paymentMethod.card_brand.charAt(0).toUpperCase() + paymentMethod.card_brand.slice(1)
    : 'Card';

  return (
    <div
      className={`relative flex items-center justify-between rounded-lg border p-4 ${
        paymentMethod.is_default
          ? 'border-indigo-500 bg-indigo-50/50 dark:border-indigo-400 dark:bg-indigo-950/20'
          : 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900'
      }`}
    >
      <div className="flex items-center gap-4">
        <div className={`${brandColor}`}>
          <CreditCard className="h-8 w-8" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {brandName} ending in {paymentMethod.card_last4}
            </span>
            {paymentMethod.is_default && (
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400">
                <Star className="h-3 w-3" />
                Default
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Expires {paymentMethod.card_exp_month}/{paymentMethod.card_exp_year}
          </p>
        </div>
      </div>

      <div className="relative">
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          disabled={loading}
          className="rounded-full p-2 hover:bg-gray-100 dark:hover:bg-gray-800"
        >
          <MoreVertical className="h-5 w-5 text-gray-400" />
        </button>

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 top-full mt-1 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-900 z-50">
              {!paymentMethod.is_default && (
                <button
                  onClick={() => {
                    onSetDefault(paymentMethod.id);
                    setMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <Star className="h-4 w-4" />
                  Set as default
                </button>
              )}
              <button
                onClick={() => {
                  onDelete(paymentMethod.id);
                  setMenuOpen(false);
                }}
                className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-gray-50 dark:text-red-400 dark:hover:bg-gray-800"
              >
                <Trash2 className="h-4 w-4" />
                Remove card
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
