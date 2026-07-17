/**
 * PaymentMethodCard component - displays a saved payment method
 */

import { CreditCard, MoreVertical, Star, Trash2 } from 'lucide-react';
import { useState } from 'react';

import type { PaymentMethod } from '@llamatrade/core/proto/billing_pb';

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

  const brandColor = CARD_BRAND_COLORS[paymentMethod.cardBrand?.toLowerCase() || 'default'];
  const brandName = paymentMethod.cardBrand
    ? paymentMethod.cardBrand.charAt(0).toUpperCase() + paymentMethod.cardBrand.slice(1)
    : 'Card';

  return (
    <div
      className={`relative flex items-center justify-between border-2 p-4 ${
        paymentMethod.isDefault
          ? 'border-orange-500 bg-orange-50 dark:border-indigo-400 dark:bg-indigo-950/20'
          : 'border-ink bg-paper dark:border-gray-700 dark:bg-gray-900'
      }`}
    >
      <div className="flex items-center gap-4">
        <div className={`${brandColor}`}>
          <CreditCard className="h-8 w-8" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink dark:text-gray-100">
              {brandName} ending in {paymentMethod.cardLast4}
            </span>
            {paymentMethod.isDefault && (
              <span className="inline-flex items-center gap-1 border border-ink bg-orange-100 px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wide text-orange-700 dark:bg-indigo-900/30 dark:text-indigo-400">
                <Star className="h-3 w-3" />
                Default
              </span>
            )}
          </div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-ink/50">
            Expires {paymentMethod.cardExpMonth}/{paymentMethod.cardExpYear}
          </p>
        </div>
      </div>

      <div className="relative">
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          disabled={loading}
          className="p-2 hover:bg-ink/5"
        >
          <MoreVertical className="h-5 w-5 text-ink/40" />
        </button>

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
            <div className="dropdown right-0 top-full mt-1 w-48 z-50">
              {!paymentMethod.isDefault && (
                <button
                  onClick={() => {
                    onSetDefault(paymentMethod.id);
                    setMenuOpen(false);
                  }}
                  className="dropdown-item w-full text-left"
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
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-500 hover:text-bone transition-colors"
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
