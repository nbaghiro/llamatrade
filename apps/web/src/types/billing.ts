/**
 * Billing and subscription types
 */

import { InvoiceStatus } from '../generated/proto/billing_pb';

export { InvoiceStatus };

export function getInvoiceStatusLabel(status: InvoiceStatus): string {
  switch (status) {
    case InvoiceStatus.DRAFT:
      return 'Draft';
    case InvoiceStatus.OPEN:
      return 'Open';
    case InvoiceStatus.PAID:
      return 'Paid';
    case InvoiceStatus.VOID:
      return 'Void';
    case InvoiceStatus.UNCOLLECTIBLE:
      return 'Uncollectible';
    default:
      return 'Unknown';
  }
}
