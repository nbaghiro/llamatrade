/** A rejected order read against the limit it broke, where the rejection names one. */

/**
 * The dollar limit a rejection message names ("over the $10,000 order limit", "exceeds max
 * order value 10000"), or null when it names none.
 */
export function limitFromMessage(message: string): number | null {
  if (!/limit|max|exceed|over/i.test(message)) return null;
  const m = message.match(/\$\s?([\d,]+(?:\.\d+)?)/) ?? message.match(/(?:limit|max(?:imum)?(?: order)?(?: value)?|of)\s*:?\s*([\d,]{4,}(?:\.\d+)?)/i);
  if (!m) return null;
  const n = Number(m[1].replace(/,/g, ''));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Whole shares that fit under a limit at a price; 0 when none do. */
export function sharesUnder(limit: number, price: number): number {
  if (!(limit > 0) || !(price > 0)) return 0;
  return Math.floor(limit / price + 1e-9);
}

export interface OrderAgainstLimit {
  value: number;
  limit: number | null;
  /** Amount over the limit; 0 when under or no limit is known. */
  over: number;
  /** Shares that would fit under the limit at the same price, when a limit is known. */
  fits: number | null;
}

export function againstLimit(quantity: number, price: number, message: string): OrderAgainstLimit {
  const value = quantity * price;
  const limit = limitFromMessage(message);
  return {
    value,
    limit,
    over: limit !== null ? Math.max(0, value - limit) : 0,
    fits: limit !== null ? sharesUnder(limit, price) : null,
  };
}
