import { num } from '@llamatrade/core/format';
import { getTenantContext, portfolioClient } from '@llamatrade/core/net';
import { useEffect, useState } from 'react';

import type { TimedValue } from './history';

export interface SleeveCurve {
  points: TimedValue[];
  /** SPY scaled to the sleeve's starting equity, on its own dates; empty when not asked for. */
  benchmark: TimedValue[];
}

export type CurveMap = Record<string, SleeveCurve | null>;

const cache = new Map<string, Promise<SleeveCurve | null>>();

function toPoints(pts: readonly { timestamp?: { seconds: bigint }; equity?: { value: string } }[]) {
  return pts
    .map((p) => ({
      t: p.timestamp?.seconds ? Number(p.timestamp.seconds) * 1000 : 0,
      v: num(p.equity),
    }))
    .filter((p) => p.t > 0)
    .sort((a, b) => a.t - b.t);
}

function load(executionId: string, benchmark: boolean): Promise<SleeveCurve | null> {
  const key = `${executionId}:${benchmark ? 'SPY' : ''}`;
  let pending = cache.get(key);
  if (!pending) {
    pending = portfolioClient
      .getStrategyEquityCurve({
        context: getTenantContext(),
        executionId,
        benchmarkSymbol: benchmark ? 'SPY' : '',
      })
      .then((res) => ({
        points: toPoints(res.equityCurve),
        benchmark: toPoints(res.benchmark?.equityCurve ?? []),
      }))
      .catch(() => {
        cache.delete(key);
        return null;
      });
    cache.set(key, pending);
  }
  return pending;
}

/**
 * Each execution's equity curve, keyed by execution id; null where it couldn't be read. Curves
 * are cached for the app's lifetime, which is fine for history that only grows at the end.
 */
export function useEquityCurves(
  executionIds: readonly string[],
  { benchmark = false }: { benchmark?: boolean } = {}
): { curves: CurveMap; loading: boolean } {
  const key = executionIds.join(',');
  const [state, setState] = useState<{ key: string; curves: CurveMap }>({ key: '', curves: {} });

  useEffect(() => {
    let live = true;
    const ids = key ? key.split(',') : [];
    Promise.all(ids.map((id) => load(id, benchmark))).then((list) => {
      if (!live) return;
      const curves: CurveMap = {};
      ids.forEach((id, i) => {
        curves[id] = list[i];
      });
      setState({ key, curves });
    });
    return () => {
      live = false;
    };
  }, [key, benchmark]);

  return { curves: state.curves, loading: state.key !== key };
}
