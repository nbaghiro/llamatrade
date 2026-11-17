import { getTenantContext, backtestClient } from '@llamatrade/core/net';
import { useEffect, useState } from 'react';

import type { TradeInput } from '../../lib/backtestView';

import { toTradeInputs } from './runData';

const PAGE = 200;

/** Every trade of each run, keyed by run id; a run whose trades fail to load maps to null. */
export function useRunTrades(ids: readonly string[]): Record<string, TradeInput[] | null> | null {
  const key = ids.join(',');
  const [out, setOut] = useState<{ key: string; trades: Record<string, TradeInput[] | null> }>();

  useEffect(() => {
    const context = getTenantContext();
    if (!key || !context) return;
    let live = true;
    const loadOne = async (id: string): Promise<TradeInput[] | null> => {
      try {
        const all = [];
        for (let page = 1; ; page++) {
          const res = await backtestClient.getBacktestTrades({
            context,
            backtestId: id,
            pagination: { page, pageSize: PAGE },
          });
          all.push(...res.trades);
          const total = res.pagination?.totalItems ?? all.length;
          if (!res.trades.length || all.length >= total) break;
        }
        return toTradeInputs(all);
      } catch {
        return null;
      }
    };
    const list = key.split(',');
    Promise.all(list.map(loadOne))
      .then((results) => {
        if (!live) return;
        setOut({ key, trades: Object.fromEntries(list.map((id, i) => [id, results[i]])) });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [key]);

  return out && out.key === key ? out.trades : null;
}
