import { useCallback } from 'react';

import { applyTokenEdit, type OutlineToken } from '../../../lib/outline';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';

import type { TokenEditHandler } from './Token';

/** Applies an edit made on an outline token to the draft; returns the reason when it can't. */
export function useTokenEdit(): TokenEditHandler {
  const store = useStrategyBuilderStoreWithContext();
  const { tree } = store;
  return useCallback(
    (token: OutlineToken, raw: string): string | null => {
      const edit = applyTokenEdit(tree, token, raw);
      switch (edit.kind) {
        case 'invalid':
          return edit.reason;
        case 'condition':
          store.updateCondition(edit.blockId, edit.condition);
          return null;
        case 'block':
          store.updateBlock(edit.blockId, edit.updates);
          return null;
        case 'filter':
          store.updateFilter(edit.blockId, edit.config);
          return null;
        case 'allocation':
          store.setWeightAllocation(edit.weightId, edit.childId, edit.percent);
          return null;
        case 'timeframe':
          store.setTimeframe(edit.value);
          return null;
        case 'benchmark':
          store.setBenchmark(edit.value);
          return null;
      }
    },
    [tree, store]
  );
}
