import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';

import { useLoad } from '../backtests/data';
import { strategyClient } from '../net/clients';

let cache: Promise<StrategyTemplate[]> | null = null;

function loadTemplates(): Promise<StrategyTemplate[]> {
  if (!cache) {
    cache = strategyClient.listTemplates({}).then((r) => r.templates);
    cache.catch(() => {
      cache = null;
    });
  }
  return cache;
}

/** Every template from ListTemplates, loaded once per app run. */
export function useTemplates() {
  return useLoad('templates', loadTemplates);
}
