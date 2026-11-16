import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useMemo } from 'react';

import {
  asFrequency,
  partialFigures,
  runLog,
  type LogLine,
  type PartialFigures,
  type RebalanceFrequency,
  type RunPhase,
} from '../../lib/backtestView';

import { eventsFromRun, phaseOf, toPartialInput, toProgressEvents } from './runData';

export interface RunView {
  phase: RunPhase;
  log: LogLine[];
  partial: PartialFigures;
  progress: number;
  currentDate: string;
  strategyName: string;
  rebalance: RebalanceFrequency | null;
}

/** Everything the run panel shows for one run, from the stream when we watched it. */
export function useRunView(run: BacktestRun | null): RunView {
  const events = useBacktestStore((s) => s.progressEvents);
  const partialMetrics = useBacktestStore((s) => s.partialMetrics);
  const startMs = useBacktestStore((s) => s.runSubmittedAt);
  const strategies = useBacktestStore((s) => s.strategies);
  const watched = useBacktestStore(
    (s) => s.currentBacktest?.id === run?.id && s.runSubmittedAt !== null
  );

  return useMemo(() => {
    const strategy = strategies.find((s) => s.id === run?.strategyId);
    const phase: RunPhase = run ? phaseOf(run.status) : 'pending';
    const source =
      watched && startMs !== null
        ? { events: toProgressEvents(events), startMs }
        : run
          ? eventsFromRun(run)
          : { events: [], startMs: Date.now() };
    const latest = [...source.events].reverse().find((e) => e.currentDate);
    return {
      phase,
      log: runLog(source.events, source.startMs),
      partial: partialFigures(watched ? toPartialInput(partialMetrics) : null),
      progress: run?.progressPercent ?? 0,
      currentDate: latest?.currentDate ?? run?.currentDate ?? '',
      strategyName: strategy?.name ?? 'Strategy',
      rebalance: asFrequency(strategy?.rebalance),
    };
  }, [run, watched, startMs, events, partialMetrics, strategies]);
}
