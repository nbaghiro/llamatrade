import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useCallback, useEffect, useRef, useState } from 'react';

import { backtestClient } from '../../services/grpc-client';
import { getTenantContext } from '../../store/auth';

const POLL_MS = 2_000;

export function isTerminal(status: BacktestStatus): boolean {
  return (
    status === BacktestStatus.COMPLETED ||
    status === BacktestStatus.FAILED ||
    status === BacktestStatus.CANCELLED
  );
}

interface RunState {
  run: BacktestRun | null;
  error: string | null;
  retry: () => void;
}

/** Reads one backtest run and polls it until it finishes. */
export function useBacktestRun(runId: string): RunState {
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      const context = getTenantContext();
      if (!context) {
        setError('Your session has ended. Please sign in again.');
        return;
      }
      try {
        const res = await backtestClient.getBacktest({ context, backtestId: runId });
        if (!live) return;
        const next = res.backtest ?? null;
        setRun(next);
        setError(next ? null : "This backtest wasn't found.");
        if (next && !isTerminal(next.status)) timer.current = setTimeout(tick, POLL_MS);
      } catch {
        if (live) setError("The backtest couldn't be loaded.");
      }
    };
    tick().catch(() => undefined);
    return () => {
      live = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [runId, attempt]);

  const retry = useCallback(() => {
    setError(null);
    setAttempt((a) => a + 1);
  }, []);

  return { run, error, retry };
}
