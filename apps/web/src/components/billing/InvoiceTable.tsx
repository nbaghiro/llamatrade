/**
 * InvoiceTable — renders the real invoices returned by the billing API, newest
 * first. Shared by the Billing (V1) and Settings (V2) surfaces; V2 additionally
 * shows the line-item description column. No rows are fabricated — an empty API
 * response renders an honest empty state.
 */

import type { Invoice } from '../../generated/proto/billing_pb';
import { getInvoiceStatusLabel, InvoiceStatus } from '../../types/billing';

import { formatDate, formatUsd, moneyToNumber, tsToDate } from './format';

interface InvoiceTableProps {
  invoices: Invoice[];
  /** V2 shows the plan/line-item description column. */
  showDescription?: boolean;
}

function invoiceTime(invoice: Invoice): number {
  return (tsToDate(invoice.periodStart) ?? tsToDate(invoice.paidAt) ?? new Date(0)).getTime();
}

/** The best human identifier the proto exposes (invoice_number is not surfaced). */
function invoiceRef(invoice: Invoice): string {
  if (invoice.stripeInvoiceId) return invoice.stripeInvoiceId;
  return invoice.id ? invoice.id.slice(0, 8).toUpperCase() : '—';
}

const HEADER_CLASS =
  'px-4 py-3 text-left font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-ink/50';

export default function InvoiceTable({ invoices, showDescription = false }: InvoiceTableProps) {
  const rows = [...invoices].sort((a, b) => invoiceTime(b) - invoiceTime(a));

  if (rows.length === 0) {
    return (
      <div className="border-2 border-ink bg-paper px-4 py-10 text-center font-mono text-[11px] uppercase tracking-wide text-ink/50">
        No invoices yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border-2 border-ink bg-paper shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <table className="w-full min-w-[640px]">
        <thead>
          <tr className="border-b-2 border-ink">
            <th className={HEADER_CLASS}>Date</th>
            {showDescription && <th className={HEADER_CLASS}>Description</th>}
            <th className={HEADER_CLASS}>Invoice</th>
            <th className={`${HEADER_CLASS} text-right`}>Amount</th>
            <th className={HEADER_CLASS}>Status</th>
            <th className={`${HEADER_CLASS} text-right`}>Receipt</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((invoice) => {
            const isPaid = invoice.status === InvoiceStatus.PAID;
            return (
              <tr key={invoice.id} className="border-b border-ink/10 last:border-0">
                <td className="px-4 py-3 font-mono text-[12px] text-ink tabular-nums">
                  {formatDate(invoice.periodStart) !== '—'
                    ? formatDate(invoice.periodStart)
                    : formatDate(invoice.paidAt)}
                </td>
                {showDescription && (
                  <td className="px-4 py-3 text-[13px] text-ink/80">
                    {invoice.items[0]?.description || 'Subscription'}
                  </td>
                )}
                <td className="px-4 py-3 font-mono text-[11px] uppercase tracking-wide text-ink/60">
                  {invoiceRef(invoice)}
                </td>
                <td className="px-4 py-3 text-right font-mono text-[12px] text-ink tabular-nums">
                  {formatUsd(moneyToNumber(invoice.amount))}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-block border border-ink px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide ${
                      isPaid ? 'bg-green-600 text-bone' : 'bg-bone text-ink'
                    }`}
                  >
                    {getInvoiceStatusLabel(invoice.status)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  {invoice.pdfUrl ? (
                    <a
                      href={invoice.pdfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-[11px] font-bold uppercase tracking-wide text-orange-600 hover:text-ink"
                    >
                      PDF
                    </a>
                  ) : (
                    <span className="font-mono text-[11px] text-ink/30">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
