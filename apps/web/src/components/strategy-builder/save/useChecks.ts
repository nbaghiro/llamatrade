import type { StrategyTree } from '@llamatrade/core/strategy/types';
import type { ValidationResult } from '@llamatrade/core/strategy/validator';
import { useEffect, useMemo, useState } from 'react';

import type { EngineCheck } from '../hooks/useEngineCheck';
import { blockLines } from '../split/rows';

import { checkItems, withFixed, type CheckItem } from './checkList';

export interface Checks {
  items: CheckItem[];
  checkedAt: Date | null;
}

/** The draft's open checks, plus the ones fixed while this page was open. */
export function useChecks(
  tree: StrategyTree,
  code: string,
  validation: ValidationResult,
  engine: EngineCheck
): Checks {
  const lines = useMemo(() => blockLines(tree, code), [tree, code]);
  const current = useMemo(
    () =>
      checkItems(
        validation.issues.map((i) => ({
          ruleId: i.ruleId,
          message: i.message,
          severity: i.severity,
          blockId: i.blockId,
        })),
        engine.status === 'problems' && engine.checked === code ? (engine.errors ?? []) : [],
        lines
      ),
    [validation.issues, engine, code, lines]
  );
  const currentKey = current.map((c) => `${c.key}@${c.line ?? ''}`).join('\n');

  const [items, setItems] = useState<CheckItem[]>(current);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  useEffect(() => {
    const now = new Date();
    setItems((prev) => withFixed(prev, current, now));
    setCheckedAt(now);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentKey]);

  return { items, checkedAt };
}
