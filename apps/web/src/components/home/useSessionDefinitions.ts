import { useEffect, useMemo, useRef, useState } from 'react';

import { getStrategy } from '../../services/strategy';
import type { SessionRow } from '../sessions/sessionRows';

export const definitionKey = (strategyId: string, version: number) => `${strategyId}@${version}`;

/** The DSL of the exact strategy version each session runs, keyed by `definitionKey`. */
export function useSessionDefinitions(rows: readonly SessionRow[]): ReadonlyMap<string, string> {
  const [defs, setDefs] = useState<ReadonlyMap<string, string>>(new Map());
  const asked = useRef(new Set<string>());
  const wanted = useMemo(
    () =>
      [
        ...new Set(
          rows
            .filter((r) => r.session.strategyId)
            .map((r) => definitionKey(r.session.strategyId, r.version))
        ),
      ].sort(),
    [rows]
  );
  const wantedKey = wanted.join(',');

  useEffect(() => {
    const missing = wantedKey.split(',').filter((k) => k && !asked.current.has(k));
    if (missing.length === 0) return;
    missing.forEach((k) => asked.current.add(k));
    Promise.all(
      missing.map(async (key) => {
        const [id, version] = key.split('@');
        try {
          const res = await getStrategy(id, Number(version) || undefined);
          return [key, res.strategy?.dslCode ?? ''] as const;
        } catch {
          return [key, ''] as const;
        }
      })
    )
      .then((pairs) => {
        setDefs((prev) => {
          const next = new Map(prev);
          for (const [k, dsl] of pairs) next.set(k, dsl);
          return next;
        });
      })
      .catch(() => undefined);
  }, [wantedKey]);

  return defs;
}
