import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { useCallback, useEffect, useState } from 'react';

import { listTemplates } from '../../services/strategy';

type Loaded =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; templates: StrategyTemplate[] };

let cache: Promise<StrategyTemplate[]> | null = null;

function load(): Promise<StrategyTemplate[]> {
  if (!cache) {
    cache = listTemplates().then((r) => r.templates);
    cache.catch(() => {
      cache = null;
    });
  }
  return cache;
}

/** Every template from ListTemplates, loaded once per page load. */
export function useTemplates(): Loaded & { retry: () => void } {
  const [state, setState] = useState<Loaded>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ status: 'loading' });
    load()
      .then((templates) => live && setState({ status: 'ready', templates }))
      .catch(() => live && setState({ status: 'error' }));
    return () => {
      live = false;
    };
  }, [attempt]);
  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { ...state, retry };
}
