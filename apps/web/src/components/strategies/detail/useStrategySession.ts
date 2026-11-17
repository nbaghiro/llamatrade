import { num, toDate } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo, useState } from 'react';

import { portfolioClient } from '../../../services/grpc-client';
import { getTenantContext } from '../../../store/auth';
import type { SessionRow } from '../../sessions/sessionRows';
import { useSessionRows } from '../../shell/useSessionRows';
import type { DatedValue } from '../sameDates';
import { pickSession } from '../stageModel';

import { fillDays, toFills, type FillDay } from './fills';

export type CurveLoad =
  | { status: 'none' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; points: DatedValue[] };

export interface StrategySession {
  /** False until the trading blotter has loaded once. */
  loaded: boolean;
  /** The live session when there is one, else the paper one. */
  row: SessionRow | null;
  curve: CurveLoad;
  days: FillDay[];
  retry: () => void;
}

const SAMPLE_MINUTES = 60;

/** The session that runs a strategy, with its equity since it started and its fills by day. */
export function useStrategySession(strategyId: string): StrategySession {
  const rows = useSessionRows();
  const loaded = useTradingStore((s) => s.loaded);
  const loading = useTradingStore((s) => s.loading);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const orders = useTradingStore((s) => s.orders);
  const [curve, setCurve] = useState<CurveLoad>({ status: 'none' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!loaded && !loading) loadBlotter().catch(() => undefined);
  }, [loaded, loading, loadBlotter]);

  const row = useMemo(() => {
    const own = rows.filter((r) => r.session.strategyId === strategyId);
    const live = pickSession(own.filter((r) => r.session.mode === ExecutionMode.LIVE));
    return live ?? pickSession(own);
  }, [rows, strategyId]);

  const executionId = row?.execution?.id ?? '';
  const startMs = row?.startedAt?.getTime() ?? 0;
  const endMs = toDate(row?.session.endedAt)?.getTime() ?? 0;

  useEffect(() => {
    if (!executionId || !startMs) {
      setCurve({ status: 'none' });
      return;
    }
    const context = getTenantContext();
    if (!context) return;
    let live = true;
    setCurve({ status: 'loading' });
    const end = endMs || Date.now();
    portfolioClient
      .getStrategyEquityCurve({
        context,
        executionId,
        timeRange: {
          start: { seconds: BigInt(Math.floor(startMs / 1000)), nanos: 0 },
          end: { seconds: BigInt(Math.floor(end / 1000)), nanos: 0 },
        },
        sampleIntervalMinutes: SAMPLE_MINUTES,
      })
      .then((r) => {
        if (!live) return;
        const points: DatedValue[] = [];
        for (const p of r.equityCurve) {
          const at = toDate(p.timestamp);
          const value = num(p.equity);
          if (at && value > 0) points.push({ at, value });
        }
        setCurve({ status: 'ready', points });
      })
      .catch(() => live && setCurve({ status: 'error' }));
    return () => {
      live = false;
    };
  }, [executionId, startMs, endMs, attempt]);

  const sessionId = row?.session.id ?? '';
  const days = useMemo(
    () => (sessionId ? fillDays(toFills(orders.filter((o) => o.sessionId === sessionId))) : []),
    [orders, sessionId]
  );

  return {
    loaded,
    row,
    curve,
    days,
    retry: () => setAttempt((a) => a + 1),
  };
}
