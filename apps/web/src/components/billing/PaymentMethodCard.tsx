import type { PaymentMethod } from '@llamatrade/core/proto/billing_pb';
import { CreditCard } from 'lucide-react';

import { cardSummary, shortYear } from './format';

interface PaymentMethodCardProps {
  paymentMethod: PaymentMethod;
  /** Omit to show the card without actions, as on the plan page. */
  onDelete?: (id: string) => void;
  loading?: boolean;
}

/** One saved card as a row: brand, last four, expiry and a Default marker. */
export default function PaymentMethodCard({
  paymentMethod: pm,
  onDelete,
  loading = false,
}: PaymentMethodCardProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 px-3.5 py-3 text-[12.5px]">
      <span className="grid h-9 w-9 flex-none place-items-center rounded-[8px] bg-sunk text-fg-2">
        <CreditCard className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <b className="num block font-semibold text-fg">{cardSummary(pm.cardBrand, pm.cardLast4)}</b>
        <span className="num block text-[11.5px] text-fg-3">
          Expires {String(pm.cardExpMonth).padStart(2, '0')}/{shortYear(pm.cardExpYear)}
        </span>
      </span>
      {pm.isDefault && <span className="badge badge-accent">Default</span>}
      {onDelete && (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={loading}
          onClick={() => onDelete(pm.id)}
        >
          Remove
        </button>
      )}
    </div>
  );
}
