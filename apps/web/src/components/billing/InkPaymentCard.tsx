/**
 * InkPaymentCard — the dark "credit card" block shown on both the Billing and
 * Settings surfaces. Ink surface, so it carries the ORANGE offset shadow
 * (never ink-on-ink). Renders the real default payment method; the surrounding
 * action buttons are supplied by each page.
 */

import type { PaymentMethod } from '../../generated/proto/billing_pb';

import { shortYear } from './format';

interface InkPaymentCardProps {
  paymentMethod: PaymentMethod | null;
  /** Cardholder, sourced from the signed-in account (proto has no name field). */
  holderName: string;
}

export default function InkPaymentCard({ paymentMethod, holderName }: InkPaymentCardProps) {
  const brand = (paymentMethod?.cardBrand || 'card').toUpperCase();
  const last4 = paymentMethod?.cardLast4 || '••••';
  const exp = paymentMethod
    ? `${String(paymentMethod.cardExpMonth).padStart(2, '0')} / ${shortYear(paymentMethod.cardExpYear)}`
    : '—';

  return (
    <div className="border-2 border-ink bg-ink text-bone shadow-[6px_6px_0_rgb(var(--lt-orange-500))]">
      <div className="flex items-start justify-between px-5 pt-5">
        <span className="font-display text-2xl uppercase tracking-[0.08em] text-bone">{brand}</span>
        {paymentMethod?.isDefault && (
          <span className="border border-orange-500 bg-orange-500 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-ink">
            Default
          </span>
        )}
      </div>

      <div className="px-5 pb-2 pt-6">
        <div className="flex items-center gap-4 font-mono text-lg tracking-[0.2em] text-bone tabular-nums">
          <span>••••</span>
          <span>••••</span>
          <span>••••</span>
          <span>{last4}</span>
        </div>
      </div>

      <div className="flex items-end justify-between border-t border-bone/15 px-5 py-4">
        <span className="font-mono text-xs uppercase tracking-[0.12em] text-bone">
          {holderName || '—'}
        </span>
        <span className="font-mono text-[11px] uppercase tracking-wide text-bone/70">
          Exp <span className="font-bold text-bone tabular-nums">{exp}</span>
        </span>
      </div>
    </div>
  );
}
