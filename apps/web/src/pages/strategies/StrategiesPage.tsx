import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { Plus, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { useSessionRows } from '../../components/shell/useSessionRows';
import { listSummary, splitByRunning } from '../../components/strategies/runningModel';
import { NotRunningSection, RunningSection } from '../../components/strategies/RunningVsBacktest';
import { StrategiesEmpty } from '../../components/strategies/StrategiesEmpty';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { NoMatch, PageHead, PanelError, Skeleton } from '../../components/ui';

const PAGE_SIZE = 100;

export default function StrategiesPage() {
  const { strategies, loading, error, fetchStrategies } = useStrategiesStore();
  const sessions = useSessionRows();
  const [query, setQuery] = useState('');
  const [requested, setRequested] = useState(false);
  const wide = useMediaQuery('(min-width: 768px)');
  const tradingLoaded = useTradingStore((s) => s.loaded);
  const tradingLoading = useTradingStore((s) => s.loading);
  const tradingError = useTradingStore((s) => s.error);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);

  useEffect(() => {
    if (!tradingLoaded && !tradingLoading) loadBlotter().catch(() => undefined);
  }, [tradingLoaded, tradingLoading, loadBlotter]);

  useEffect(() => {
    useStrategiesStore.setState({
      pageSize: PAGE_SIZE,
      page: 1,
      statusFilter: 'all',
      searchQuery: '',
    });
    setRequested(true);
    fetchStrategies().catch(() => undefined);
  }, [fetchStrategies]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return strategies;
    return strategies.filter(
      (s) =>
        s.name.toLowerCase().includes(q) || s.symbols.some((sym) => sym.toLowerCase().includes(q))
    );
  }, [strategies, query]);

  const all = useMemo(() => splitByRunning(strategies, sessions), [strategies, sessions]);
  const split = useMemo(() => splitByRunning(shown, sessions), [shown, sessions]);
  const summary = listSummary(all.running.length, all.notRunning.length);

  const firstLoad =
    ((!requested || loading) && strategies.length === 0) ||
    (strategies.length > 0 && !tradingLoaded && !tradingError);

  if (!firstLoad && !error && strategies.length === 0) {
    return (
      <div className="page relative isolate">
        <PageHead
          title="Make your first strategy"
          documentTitle="Strategies"
          sub={
            <span className="block max-w-[640px] text-[15px]">
              A strategy is a short set of rules for what to hold and when to rebalance. Pick a way
              to start. Each one ends with a draft you can backtest.
            </span>
          }
        />
        <StrategiesEmpty />
      </div>
    );
  }

  const search = (
    <label className="flex h-9 min-w-0 items-center gap-2 rounded-full border border-line-strong bg-panel px-3.5 focus-within:border-accent max-md:w-full md:w-[230px]">
      <Search className="h-4 w-4 flex-none text-fg-3" aria-hidden="true" />
      <span className="sr-only">Search names and symbols</span>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search names and symbols"
        className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-fg-3"
      />
    </label>
  );

  return (
    <div className="page relative isolate">
      <PageHead
        title="Strategies"
        sub={firstLoad ? ' ' : summary}
        actions={
          <>
            {search}
            <Link to="/strategies/templates" className="btn btn-secondary">
              Templates
            </Link>
            <Link to="/strategies/builder" className="btn btn-primary">
              <Plus className="h-4 w-4" />
              New strategy
            </Link>
          </>
        }
      />

      {firstLoad ? (
        <div aria-busy="true" className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="panel grid gap-3 px-4 py-4">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-[110px] w-full" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="panel">
          <PanelError
            title="Strategies couldn’t be loaded"
            cause={error}
            onRetry={() => {
              fetchStrategies().catch(() => undefined);
            }}
          />
        </div>
      ) : shown.length === 0 ? (
        <div className="panel">
          <NoMatch
            noun="strategies"
            query={query}
            filters={[]}
            total={strategies.length}
            onClear={() => setQuery('')}
          />
        </div>
      ) : (
        <>
          <RunningSection items={split.running} wide={wide} />
          <NotRunningSection strategies={split.notRunning} sessions={sessions} wide={wide} />
        </>
      )}
    </div>
  );
}
