import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import { toDate, toNumber, toTimestamp } from '@llamatrade/core/stores/backtest';
import type { BlockId, StrategyTree } from '@llamatrade/core/strategy/types';
import { useEffect, useMemo, useState } from 'react';

import { marketDataClient } from '../../../services/grpc-client';
import { rebalanceEvery, rebalanceIndexes } from '../../strategy-builder/blocks/conditionHistory';

import {
  conditionHistory,
  countAtRebalances,
  latestReading,
  operandWarmup,
  readableIfs,
  readableSymbols,
  type ConditionHistory,
  type DailySeries,
  type Reading,
  type RebalanceCount,
} from './evaluate';

const DAY_MS = 86_400_000;
const TWO_YEARS_DAYS = 731;
const cache = new Map<string, Promise<DailySeries>>();

function loadCloses(symbol: string, from: Date): Promise<DailySeries> {
  const day = from.toISOString().slice(0, 10);
  const key = `${symbol}|${day}|${new Date().toISOString().slice(0, 10)}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const p = marketDataClient
    .getHistoricalBars({
      symbol,
      timeframe: Timeframe.TIMEFRAME_1DAY,
      start: toTimestamp(from),
      end: toTimestamp(new Date()),
      adjustForSplits: true,
      pagination: { page: 1, pageSize: 5000 },
    })
    .then((res) => {
      const dates: Date[] = [];
      const closes: number[] = [];
      for (const b of res.bars) {
        const at = toDate(b.timestamp);
        if (!at) continue;
        dates.push(at);
        closes.push(toNumber(b.close));
      }
      return { dates, closes };
    });
  p.catch(() => cache.delete(key));
  cache.set(key, p);
  return p;
}

export interface RuleReading {
  history: ConditionHistory;
  today: Reading | null;
  rebalances: RebalanceCount;
  /** What the count covers: the backtest's dates, or the last two years. */
  window: { from: Date; to: Date; source: 'backtest' | 'recent' };
}

export type Readings =
  | { status: 'none' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; byBlock: ReadonlyMap<BlockId, RuleReading> };

/**
 * Today's reading of each rule that daily closes can answer, and how often it held at the
 * strategy's rebalances over `window` (a backtest's dates) or the last two years.
 */
export function useRuleReadings(
  tree: StrategyTree | null,
  timeframe: string,
  window: { from: Date; to: Date } | null
): Readings {
  const ifs = useMemo(() => (tree ? readableIfs(tree) : []), [tree]);
  const symbols = useMemo(() => (tree ? readableSymbols(tree) : []), [tree]);
  const warm = Math.max(
    0,
    ...ifs.map((b) => Math.max(operandWarmup(b.condition.left), operandWarmup(b.condition.right)))
  );
  const fromMs = window?.from.getTime() ?? null;
  const toMs = window?.to.getTime() ?? null;
  const [state, setState] = useState<Readings>({ status: 'none' });

  useEffect(() => {
    if (!tree || ifs.length === 0) {
      setState({ status: 'none' });
      return;
    }
    let live = true;
    setState({ status: 'loading' });
    const now = Date.now();
    const countFrom = fromMs ?? now - TWO_YEARS_DAYS * DAY_MS;
    const fetchFrom = new Date(countFrom - Math.ceil(warm * 1.6 + 10) * DAY_MS);
    Promise.all(symbols.map((s) => loadCloses(s, fetchFrom).then((d) => [s, d] as const)))
      .then((pairs) => {
        if (!live) return;
        const bars = new Map(pairs);
        const out = new Map<BlockId, RuleReading>();
        const win = {
          from: new Date(countFrom),
          to: toMs !== null ? new Date(toMs) : new Date(now),
          source: fromMs !== null ? ('backtest' as const) : ('recent' as const),
        };
        for (const b of ifs) {
          const h = conditionHistory(b.condition, bars);
          if (!h) continue;
          const idx = rebalanceIndexes(h.dates, rebalanceEvery(timeframe)).filter(
            (i) => h.dates[i].getTime() <= win.to.getTime()
          );
          out.set(b.id, {
            history: h,
            today: latestReading(h),
            rebalances: countAtRebalances(h, idx, win.from),
            window: win,
          });
        }
        setState({ status: 'ready', byBlock: out });
      })
      .catch(() => live && setState({ status: 'error' }));
    return () => {
      live = false;
    };
  }, [tree, ifs, symbols, warm, timeframe, fromMs, toMs]);

  return state;
}
