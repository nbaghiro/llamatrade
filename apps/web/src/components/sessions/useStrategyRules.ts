import { getTenantContext, strategyClient } from '@llamatrade/core/net';
import { useEffect, useState } from 'react';

/** A strategy version's rules as written, or null until read (or when they can't be). */
export function useStrategyRules(strategyId: string, version: number): string | null {
  const [dsl, setDsl] = useState<{ key: string; code: string } | null>(null);
  const key = `${strategyId}:${version}`;
  useEffect(() => {
    if (!strategyId) return;
    let live = true;
    strategyClient
      .getStrategy({ context: getTenantContext(), strategyId, version })
      .then((res) => {
        if (live) setDsl({ key, code: res.strategy?.dslCode ?? '' });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [key, strategyId, version]);
  return dsl?.key === key ? dsl.code : null;
}
