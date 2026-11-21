import { num, toDate } from '@llamatrade/core/format';
import { Timeframe } from '@llamatrade/core/proto/market_data_pb';

import { marketDataClient } from '../net/clients';
import type { Point } from './model';

const cache = new Map<string, Promise<Point[]>>();

const ts = (t: number) => ({ seconds: BigInt(Math.floor(t / 1000)), nanos: 0 });

/** Daily closes for a symbol between two dates, split-adjusted, cached per day range. */
export function loadDailyCloses(symbol: string, start: number, end: number): Promise<Point[]> {
  const key = `${symbol}:${Math.floor(start / 86_400_000)}:${Math.floor(end / 86_400_000)}`;
  let p = cache.get(key);
  if (!p) {
    p = marketDataClient
      .getHistoricalBars({
        symbol,
        timeframe: Timeframe.TIMEFRAME_1DAY,
        start: ts(start),
        end: ts(end),
        adjustForSplits: true,
        pagination: { page: 1, pageSize: 5000 },
      })
      .then((r) => {
        const out: Point[] = [];
        for (const b of r.bars) {
          const at = toDate(b.timestamp)?.getTime();
          const value = num(b.close);
          if (at !== undefined && value > 0) out.push({ at, value });
        }
        return out.sort((a, b) => a.at - b.at);
      });
    p.catch(() => cache.delete(key));
    cache.set(key, p);
  }
  return p;
}
