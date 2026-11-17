import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useCallback, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import {
  parseScope,
  resolveScope,
  SCOPE_PARAM,
  scopeChoices,
  type AccountScope,
} from '../../lib/scope';
import type { ScopeOption } from '../ui/ScopeControl';

const STORAGE_PREFIX = 'llamatrade-scope:';

function remembered(page: string): AccountScope | null {
  try {
    return parseScope(window.localStorage.getItem(STORAGE_PREFIX + page));
  } catch {
    return null;
  }
}

function remember(page: string, scope: AccountScope) {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + page, scope);
  } catch {
    // Storage can be unavailable in private windows; the address still carries the choice.
  }
}

export interface PageScope {
  scope: AccountScope;
  setScope: (scope: AccountScope) => void;
  /** Ready for `ScopeControl`; empty until the accounts load. */
  options: ScopeOption[];
}

/**
 * This page's account scope (mode2 A). It is read from `?scope=` first, then from what this
 * page used last, and every change is written to both. Balances, when the page knows them,
 * show under each choice.
 */
export function usePageScope(
  page: string,
  balances?: Partial<Record<AccountScope, number>>
): PageScope {
  const [params, setParams] = useSearchParams();
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const loading = useBrokerStore((s) => s.loading);
  const fetchCredentials = useBrokerStore((s) => s.fetch);

  useEffect(() => {
    if (!loaded && !loading) fetchCredentials().catch(() => undefined);
  }, [loaded, loading, fetchCredentials]);

  const choices = useMemo(
    () =>
      scopeChoices(
        credentials
          .filter((c) => c.isActive)
          .map((c) => ({ isPaper: c.isPaper, keyPrefix: c.apiKeyPrefix }))
      ),
    [credentials]
  );

  const scope = resolveScope(
    parseScope(params.get(SCOPE_PARAM)),
    typeof window === 'undefined' ? null : remembered(page),
    choices.map((c) => c.key)
  );

  const setScope = useCallback(
    (next: AccountScope) => {
      remember(page, next);
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          p.set(SCOPE_PARAM, next);
          return p;
        },
        { replace: true }
      );
    },
    [page, setParams]
  );

  const options = useMemo<ScopeOption[]>(
    () =>
      choices.map((c) => {
        const v = balances?.[c.key];
        return { ...c, detail: v === undefined ? undefined : formatMoney(v) };
      }),
    [choices, balances]
  );

  return { scope, setScope, options };
}
