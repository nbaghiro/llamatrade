import { heldSymbolsOn, type HoldingLane } from './annotations';

export type DefensiveKind = 'bonds' | 'gold' | 'cash';

/** Funds that read as stepping out of stocks; anything else counts as stocks. */
const DEFENSIVE: Record<string, DefensiveKind> = {
  TLT: 'bonds',
  IEF: 'bonds',
  IEI: 'bonds',
  SHY: 'bonds',
  BND: 'bonds',
  AGG: 'bonds',
  TIP: 'bonds',
  GOVT: 'bonds',
  VGLT: 'bonds',
  VGIT: 'bonds',
  VGSH: 'bonds',
  EDV: 'bonds',
  GLD: 'gold',
  IAU: 'gold',
  GLDM: 'gold',
  SGOL: 'gold',
  BIL: 'cash',
  SGOV: 'cash',
  SHV: 'cash',
};

export const defensiveKind = (symbol: string): DefensiveKind | null => DEFENSIVE[symbol] ?? null;

export interface DefensiveStretch {
  from: Date;
  to: Date;
  symbols: string[];
}

/** Stretches of `dates` on which everything held was a bond, gold or cash fund. */
export function defensiveStretches(
  lanes: readonly HoldingLane[],
  dates: readonly Date[]
): DefensiveStretch[] {
  const out: DefensiveStretch[] = [];
  let open: DefensiveStretch | null = null;
  for (const d of dates) {
    const held = heldSymbolsOn(lanes, d);
    const defensive = held.length > 0 && held.every((s) => defensiveKind(s) !== null);
    if (defensive) {
      if (open) {
        open.to = d;
        for (const s of held) if (!open.symbols.includes(s)) open.symbols.push(s);
      } else {
        open = { from: d, to: d, symbols: [...held] };
      }
    } else if (open) {
      out.push(open);
      open = null;
    }
  }
  if (open) out.push(open);
  return out.map((s) => ({ ...s, symbols: [...s.symbols].sort() }));
}

/** Share of `dates` on which at least one stock fund was held; null without dates. */
export function inStocksShare(
  lanes: readonly HoldingLane[],
  dates: readonly Date[]
): number | null {
  if (!dates.length) return null;
  const n = dates.filter((d) =>
    heldSymbolsOn(lanes, d).some((s) => defensiveKind(s) === null)
  ).length;
  return n / dates.length;
}

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];

/** "six" for 6, "14" past ten. */
export const numberWord = (n: number): string => WORDS[n] ?? String(n);

/** "bonds and gold", "bonds, gold and cash". */
export function joinWords(words: readonly string[]): string {
  if (words.length <= 1) return words[0] ?? '';
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

const DAY_MS = 86_400_000;

function lengthWords(days: number): { n: number; unit: 'day' | 'week' | 'month' } {
  if (days >= 28) return { n: Math.max(1, Math.round(days / 30.4)), unit: 'month' };
  if (days >= 7) return { n: Math.round(days / 7), unit: 'week' };
  return { n: Math.max(1, Math.round(days)), unit: 'day' };
}

/** "for one to three months each time", "for two weeks", "for one day to two months each time". */
export function durationPhrase(daysList: readonly number[]): string {
  if (!daysList.length) return '';
  const lo = lengthWords(Math.min(...daysList));
  const hi = lengthWords(Math.max(...daysList));
  const unit = (u: string, n: number) => (n === 1 ? u : `${u}s`);
  if (lo.unit === hi.unit && lo.n === hi.n) {
    return `for ${numberWord(lo.n)} ${unit(lo.unit, lo.n)}${daysList.length > 1 ? ' each time' : ''}`;
  }
  const from =
    lo.unit === hi.unit ? numberWord(lo.n) : `${numberWord(lo.n)} ${unit(lo.unit, lo.n)}`;
  return `for ${from} to ${numberWord(hi.n)} ${unit(hi.unit, hi.n)} each time`;
}

/** "It moved into bonds and gold six times, for one to three months each time." */
export function switchSentence(stretches: readonly DefensiveStretch[]): string | null {
  if (!stretches.length) return null;
  const kinds = [
    ...new Set(
      stretches.flatMap((s) => s.symbols.map((x) => defensiveKind(x)).filter((k) => k !== null))
    ),
  ];
  const order: DefensiveKind[] = ['bonds', 'gold', 'cash'];
  const named = joinWords(order.filter((k) => kinds.includes(k)));
  const times = stretches.length === 1 ? 'once' : `${numberWord(stretches.length)} times`;
  const days = stretches.map((s) => Math.max(1, (s.to.getTime() - s.from.getTime()) / DAY_MS));
  return `It moved into ${named} ${times}, ${durationPhrase(days)}.`;
}

/** How the run's worst drawdown reads against the benchmark's, both negative fractions. */
export function drawdownPhrase(run: number, bench: number, benchName: string): string {
  const r = bench === 0 ? Infinity : Math.abs(run) / Math.abs(bench);
  if (r <= 0.5) return `less than half of ${benchName}'s worst drawdown`;
  if (r < 0.95) return `a smaller worst drawdown than ${benchName}`;
  if (r <= 1.05) return `about the same worst drawdown as ${benchName}`;
  return `a deeper worst drawdown than ${benchName}`;
}

/** "To TLT and GLD". */
export const toSymbolsLabel = (symbols: readonly string[]) => `To ${joinWords(symbols)}`;
