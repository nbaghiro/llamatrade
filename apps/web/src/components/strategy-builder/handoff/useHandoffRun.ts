import {
  BacktestStatus,
  type BacktestConfig,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import { DEFAULT_BACKTEST_COSTS, toDecimal, toTimestamp } from '@llamatrade/core/stores/backtest';
import { useCallback, useEffect, useRef, useState } from 'react';

import { backtestClient } from '../../../services/grpc-client';
import { getTenantContext } from '../../../store/auth';

export type HandoffPhase = 'idle' | 'running' | 'done' | 'failed';

export interface HandoffState {
  phase: HandoffPhase;
  /** The run of the new version, as last read. */
  run: BacktestRun | null;
  /** The run whose settings were reused, to compare against. */
  base: BacktestRun | null;
  error: string | null;
}

const POLL_MS = 2000;
const TERMINAL = new Set([
  BacktestStatus.COMPLETED,
  BacktestStatus.FAILED,
  BacktestStatus.CANCELLED,
]);

/** The settings a run with no earlier run to copy uses: two years to today, $10,000, SPY. */
export function defaultSettings(today = new Date()): {
  start: Date;
  end: Date;
  capital: number;
} {
  const start = new Date(today);
  start.setFullYear(start.getFullYear() - 2);
  return { start, end: today, capital: 10_000 };
}

/** The request for a new version: the base run's settings with only the version changed. */
export function handoffConfig(
  strategyId: string,
  version: number,
  base: BacktestConfig | undefined,
  today = new Date()
) {
  if (base) {
    return {
      ...base,
      strategyId,
      strategyVersion: version,
    };
  }
  const d = defaultSettings(today);
  return {
    strategyId,
    strategyVersion: version,
    startDate: toTimestamp(d.start),
    endDate: toTimestamp(d.end),
    initialCapital: toDecimal(d.capital),
    symbols: [],
    commission: toDecimal(DEFAULT_BACKTEST_COSTS.commission),
    slippagePercent: toDecimal(DEFAULT_BACKTEST_COSTS.slippage),
    timeframe: '1D',
    allowShorting: false,
    useAdjustedPrices: true,
    parameters: {},
    benchmarkSymbol: 'SPY',
    includeBenchmark: true,
  };
}

/** handoff2 A: run a saved version with the last run's settings and follow it to the end. */
export function useHandoffRun() {
  const [state, setState] = useState<HandoffState>({
    phase: 'idle',
    run: null,
    base: null,
    error: null,
  });
  const seq = useRef(0);
  useEffect(
    () => () => {
      seq.current++;
    },
    []
  );

  const start = useCallback(
    async (strategyId: string, version: number, base: BacktestRun | null) => {
      const id = ++seq.current;
      setState({ phase: 'running', run: null, base, error: null });
      const context = getTenantContext();
      try {
        const res = await backtestClient.runBacktest({
          context,
          config: handoffConfig(strategyId, version, base?.config),
        });
        let run = res.backtest ?? null;
        if (!run) throw new Error('The backtest didn’t start.');
        while (id === seq.current && !TERMINAL.has(run.status)) {
          setState((s) => ({ ...s, run }));
          await new Promise((r) => setTimeout(r, POLL_MS));
          const got = await backtestClient.getBacktest({ context, backtestId: run.id });
          run = got.backtest ?? run;
        }
        if (id !== seq.current) return;
        setState({
          phase: run.status === BacktestStatus.COMPLETED ? 'done' : 'failed',
          run,
          base,
          error:
            run.status === BacktestStatus.COMPLETED
              ? null
              : run.statusMessage || 'The backtest stopped before it finished.',
        });
      } catch (e) {
        if (id !== seq.current) return;
        setState((s) => ({
          ...s,
          phase: 'failed',
          error: e instanceof Error ? e.message : 'The backtest couldn’t start.',
        }));
      }
    },
    []
  );

  const reset = useCallback(() => {
    seq.current++;
    setState({ phase: 'idle', run: null, base: null, error: null });
  }, []);

  return { ...state, start, reset };
}
