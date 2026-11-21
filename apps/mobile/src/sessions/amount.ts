/** Dollar amounts typed into the Start and Run on live screens. */

/** "15,000.50" or "$15000" as 15000.5; null for anything that isn't a positive amount. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Why an amount can't be used, or null when it can. Compared at cent precision. */
export function amountProblem(amount: number | null, available: number | null): string | null {
  if (amount === null) return 'Enter an amount greater than $0.';
  if (available !== null && Math.round(amount * 100) > Math.round(available * 100)) {
    return 'That is more than the free cash on this account. Lower the amount or add funds first.';
  }
  return null;
}

/** A starting suggestion: half the free cash, rounded down to $1,000, at least $1,000 when there's that much. */
export function suggestAmount(available: number): number {
  if (!(available > 0)) return 0;
  if (available < 1000) return Math.floor(available);
  return Math.max(1000, Math.floor(available / 2 / 1000) * 1000);
}
