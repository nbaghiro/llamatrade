import { ConnectError } from '@connectrpc/connect';
import { getTenantContext, ledgerClient } from '@llamatrade/core/net';

/** How much of new or unallocated cash goes to each sleeve, by ledger sleeve id. */
export type Placement = Record<string, number>;

export function placed(placement: Placement): number {
  return Object.values(placement).reduce((s, v) => s + (Number.isFinite(v) && v > 0 ? v : 0), 0);
}

/** Why a placement can't go ahead, or null when it can. */
export function placementProblem(available: number, placement: Placement): string | null {
  const total = placed(placement);
  if (total <= 0) return 'Enter an amount for at least one sleeve.';
  if (total > available + 0.005) {
    return `That's ${formatUsd(total - available)} more than is available.`;
  }
  return null;
}

function formatUsd(v: number): string {
  return v.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

export interface BarPart {
  id: string;
  value: number;
  /** The part this change adds to, drawn hatched in the after bar. */
  added?: boolean;
}

/**
 * The paper account before and after: each sleeve then unallocated cash. New money not placed in
 * a sleeve lands in unallocated cash; placed money moves out of it.
 */
export function beforeAfter(
  sleeves: readonly { id: string; value: number }[],
  unallocated: number,
  deposit: number,
  placement: Placement
): { now: BarPart[]; after: BarPart[] } {
  const moved = placed(placement);
  const now = [
    ...sleeves.map((s) => ({ id: s.id, value: s.value })),
    { id: 'unallocated', value: unallocated },
  ];
  const after: BarPart[] = [];
  for (const s of sleeves) {
    after.push({ id: s.id, value: s.value });
    const add = placement[s.id] ?? 0;
    if (add > 0) after.push({ id: `${s.id}+`, value: add, added: true });
  }
  after.push({
    id: 'unallocated',
    value: Math.max(0, unallocated + deposit - moved),
    added: deposit - moved > 0,
  });
  return { now, after };
}

/** Moves unallocated paper cash into a sleeve; returns an error sentence, or null when it worked. */
export async function allocateToSleeve(
  accountId: string,
  sleeveId: string,
  amount: number
): Promise<string | null> {
  try {
    await ledgerClient.allocateCapital({
      context: getTenantContext(),
      accountId,
      toSleeveId: sleeveId,
      amount: { value: amount.toFixed(2) },
      requestId: crypto.randomUUID(),
    });
    return null;
  } catch (e) {
    return e instanceof ConnectError ? e.rawMessage : 'The top-up could not be made.';
  }
}
