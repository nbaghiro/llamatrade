/** Portfolio as plain data: estimated rebalance orders, statement rows and lanes by day. Pure, for the tests. */

export interface HoldingIn {
  symbol: string;
  qty: number;
  price: number;
  marketValue: number;
}

export interface EstimatedOrder {
  symbol: string;
  side: 'buy' | 'sell';
  shares: number;
}

/**
 * What a fixed-weight rebalance would place at the latest prices: each symbol moved to its
 * target share of the sleeve's value (holdings plus cash), in whole shares. An estimate only;
 * the session prices its orders when it runs.
 */
export function estimateOrders(holdings: readonly HoldingIn[], targets: Readonly<Record<string, number>>, cash: number): EstimatedOrder[] {
  const symbols = Object.keys(targets);
  if (symbols.length === 0) return [];
  const value = holdings.reduce((sum, h) => sum + (Number.isFinite(h.marketValue) ? h.marketValue : 0), 0) + (Number.isFinite(cash) ? cash : 0);
  if (!(value > 0)) return [];
  const out: EstimatedOrder[] = [];
  const all = new Set([...symbols, ...holdings.map((h) => h.symbol)]);
  for (const symbol of [...all].sort()) {
    const h = holdings.find((x) => x.symbol === symbol);
    const price = h?.price ?? 0;
    if (!(price > 0)) continue;
    const want = (targets[symbol] ?? 0) * value;
    const have = h?.marketValue ?? 0;
    const shares = Math.trunc((want - have) / price);
    if (shares !== 0) out.push({ symbol, side: shares > 0 ? 'buy' : 'sell', shares: Math.abs(shares) });
  }
  return out;
}

/** "buy 5 TLT and sell 2 GLD" */
export function ordersSentence(orders: readonly EstimatedOrder[]): string {
  const parts = orders.map((o) => `${o.side} ${o.shares} ${o.symbol}`);
  if (parts.length <= 1) return parts.join('');
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

export interface StatementIn {
  id: string;
  kind: string;
  label: string;
  sublabel: string;
  signed: number;
  amount: number;
  t: number;
  account: 'live' | 'paper' | null;
  sleeveId: string;
}

export interface StatementDay {
  day: number;
  rows: StatementIn[];
}

/** Rows grouped by day, newest day first and newest row first inside it. */
export function groupByDay(rows: readonly StatementIn[]): StatementDay[] {
  const map = new Map<number, StatementIn[]>();
  for (const r of rows) {
    const d = new Date(r.t);
    d.setHours(0, 0, 0, 0);
    const key = d.getTime();
    const list = map.get(key) ?? [];
    list.push(r);
    map.set(key, list);
  }
  return [...map.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([day, list]) => ({ day, rows: list.sort((a, b) => b.t - a.t) }));
}

/** Short tag for a statement row. */
export function statementTag(kind: string): string {
  switch (kind) {
    case 'buy':
      return 'BUY';
    case 'sell':
      return 'SELL';
    case 'deposit':
      return 'IN';
    case 'withdrawal':
      return 'OUT';
    case 'allocation':
      return 'TO';
    case 'release':
      return 'BACK';
    case 'dividend':
      return 'DIV';
    case 'interest':
      return 'INT';
    case 'fee':
      return 'FEE';
    default:
      return 'TXN';
  }
}

/** Row counts per sleeve per day, for lanes above the statement. */
export function dayCounts(rows: readonly StatementIn[]): Map<string, { day: number; count: number }[]> {
  const bySleeve = new Map<string, Map<number, number>>();
  for (const r of rows) {
    const key = r.sleeveId || 'cash';
    const d = new Date(r.t);
    d.setHours(0, 0, 0, 0);
    const days = bySleeve.get(key) ?? new Map<number, number>();
    days.set(d.getTime(), (days.get(d.getTime()) ?? 0) + 1);
    bySleeve.set(key, days);
  }
  const out = new Map<string, { day: number; count: number }[]>();
  for (const [k, days] of bySleeve) {
    out.set(
      k,
      [...days.entries()].sort((a, b) => a[0] - b[0]).map(([day, count]) => ({ day, count })),
    );
  }
  return out;
}

/** Parses a typed dollar amount ("10,000", "$2500.50"); null when it isn't a positive number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return n > 0 && Number.isFinite(n) ? n : null;
}
