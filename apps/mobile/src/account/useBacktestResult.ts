import { backtestClient, getTenantContext, strategyClient } from '@llamatrade/core/net';
import type { BacktestRun, BacktestTrade, EquityPoint } from '@llamatrade/core/proto/backtest_pb';
import type { Timestamp } from '@llamatrade/core/proto/common_pb';
import { errorMessage } from '@llamatrade/core/errors';
import { useCallback, useEffect, useState } from 'react';

import type { TradeLeg } from './firstResult';

export interface ResultSeries {
  dates: Date[];
  values: number[];
  benchmark: number[];
  benchmarkSymbol: string;
}

export interface BacktestResultState {
  run: BacktestRun | null;
  name: string;
  series: ResultSeries | null;
  trades: TradeLeg[] | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const toDate = (ts?: Timestamp): Date | null => (ts?.seconds ? new Date(Number(ts.seconds) * 1000) : null);
const num = (d?: { value: string }): number => (d?.value ? parseFloat(d.value) || 0 : 0);

function seriesOf(points: readonly EquityPoint[]): { dates: Date[]; values: number[] } {
  const dates: Date[] = [];
  const values: number[] = [];
  for (const p of points) {
    const at = toDate(p.timestamp);
    if (!at) continue;
    dates.push(at);
    values.push(num(p.equity));
  }
  return { dates, values };
}

async function allTrades(backtestId: string): Promise<BacktestTrade[]> {
  const context = getTenantContext();
  const all: BacktestTrade[] = [];
  for (let page = 1; page < 50; page++) {
    const res = await backtestClient.getBacktestTrades({ context, backtestId, pagination: { page, pageSize: 200 } });
    all.push(...res.trades);
    const total = res.pagination?.totalItems ?? all.length;
    if (res.trades.length === 0 || all.length >= total) break;
  }
  return all;
}

/** One backtest with its equity, SPY and trades, read without touching the shared backtest store. */
export function useBacktestResult(id: string): BacktestResultState {
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [name, setName] = useState('');
  const [series, setSeries] = useState<ResultSeries | null>(null);
  const [trades, setTrades] = useState<TradeLeg[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    const context = getTenantContext();
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await backtestClient.getBacktest({ context, backtestId: id });
        const bt = res.backtest ?? null;
        if (!live) return;
        setRun(bt);
        const results = bt?.results;
        if (results) {
          const main = seriesOf(results.equityCurve);
          const bench = seriesOf(results.benchmarkEquityCurve);
          setSeries({
            dates: main.dates,
            values: main.values,
            benchmark: bench.values.length === main.values.length ? bench.values : [],
            benchmarkSymbol: results.benchmarkSymbol,
          });
        }
        if (bt?.strategyId) {
          strategyClient
            .getStrategy({ context, strategyId: bt.strategyId, version: 0 })
            .then((r) => live && setName(r.strategy?.name ?? ''))
            .catch(() => undefined);
        }
        const legs = await allTrades(id);
        if (!live) return;
        setTrades(legs.map((t) => ({ symbol: t.symbol, entryTime: toDate(t.entryTime), exitTime: toDate(t.exitTime) })));
      } catch (e) {
        if (live) setError(errorMessage(e));
      } finally {
        if (live) setLoading(false);
      }
    })().catch(() => undefined);
    return () => {
      live = false;
    };
  }, [id, attempt]);

  return { run, name, series, trades, loading, error, reload };
}
