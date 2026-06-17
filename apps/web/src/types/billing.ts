/**
 * Billing and subscription types
 */

// Import enum types from proto-generated code (single source of truth)
import { InvoiceStatus } from '../generated/proto/billing_pb';

// Re-export proto enums
export { InvoiceStatus };

// ============================================
// Enum Display Helpers
// ============================================

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
