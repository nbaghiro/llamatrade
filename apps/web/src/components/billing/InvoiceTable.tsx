import type { Invoice } from '@llamatrade/core/proto/billing_pb';

import { getInvoiceStatusLabel, InvoiceStatus } from '../../types/billing';

import { formatDate, formatUsd, moneyToNumber, tsToDate } from './format';

interface InvoiceTableProps {
  invoices: Invoice[];
}

function invoiceTime(invoice: Invoice): number {
  return (tsToDate(invoice.periodStart) ?? tsToDate(invoice.paidAt) ?? new Date(0)).getTime();
}

const ATTENTION = new Set([InvoiceStatus.OPEN, InvoiceStatus.UNCOLLECTIBLE]);

const TH = 'border-b border-line px-3.5 py-2 text-left text-[11px] font-medium text-fg-3';
const TD = 'border-b border-line px-3.5 py-2';

/** The invoices the billing service returns, newest first. Shows an honest empty state. */
export default function InvoiceTable({ invoices }: InvoiceTableProps) {
  const rows = [...invoices].sort((a, b) => invoiceTime(b) - invoiceTime(a));

  if (rows.length === 0) {
    return (
      <p className="m-0 px-6 py-[22px] text-center text-[12.5px] text-fg-2">No invoices yet.</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12.5px]">
        <thead>
          <tr>
            <th className={TH}>Date</th>
            <th className={`${TH} text-right`}>Amount</th>
            <th className={TH}>Status</th>
            <th className={`${TH} text-right`}>Receipt</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((invoice) => {
            const date =
              formatDate(invoice.periodStart) !== '–'
                ? formatDate(invoice.periodStart)
                : formatDate(invoice.paidAt);
            return (
              <tr key={invoice.id} className="[&:last-child>td]:border-b-0">
                <td className={TD}>
                  <span className="num block whitespace-nowrap text-fg">{date}</span>
                  {invoice.items[0]?.description && (
                    <span className="block text-[11px] text-fg-3">
                      {invoice.items[0].description}
                    </span>
                  )}
                </td>
                <td className={`${TD} num whitespace-nowrap text-right text-fg`}>
                  {formatUsd(moneyToNumber(invoice.amount))}
                </td>
                <td
                  className={`${TD} ${ATTENTION.has(invoice.status) ? 'text-risk' : 'text-fg-2'}`}
                >
                  {getInvoiceStatusLabel(invoice.status)}
                </td>
                <td className={`${TD} text-right`}>
                  {invoice.pdfUrl ? (
                    <a
                      href={invoice.pdfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      PDF
                    </a>
                  ) : (
                    <span className="text-fg-3">–</span>
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
