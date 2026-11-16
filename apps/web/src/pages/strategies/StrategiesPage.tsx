import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { Plus, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { StrategiesEmpty } from '../../components/strategies/StrategiesEmpty';
import { StrategyListRow } from '../../components/strategies/StrategyListRow';
import { StrategyOverview } from '../../components/strategies/StrategyOverview';
import {
  LIST_FILTERS,
  matchesFilter,
  runState,
  stateLabel,
  type ListFilter,
} from '../../components/strategies/strategyView';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { useStrategyDetail } from '../../components/strategies/useStrategyDetail';
import {
  NoMatch,
  PageArt,
  PanelError,
  Segmented,
  Skeleton,
  SkeletonChart,
} from '../../components/ui';
import { useUIStore } from '../../store/ui';

const PAGE_SIZE = 100;

function SelectedOverview({ id }: { id: string }) {
  const detail = useStrategyDetail(id);
  if (!detail.strategy) {
    if (detail.status === 'error') {
      return <PanelError title="This strategy couldn’t be loaded" onRetry={detail.retry} />;
    }
    return (
      <div className="grid gap-4" aria-busy="true">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-3 w-80" />
        <SkeletonChart height={130} />
      </div>
    );
  }
  return (
    <StrategyOverview
      strategy={detail.strategy}
      state={detail.state}
      stateLabel={detail.stateLabel}
      meta={detail.meta}
      run={detail.run}
      session={detail.session}
    />
  );
}

export default function StrategiesPage() {
  const { strategies, deployments, loading, error, total, fetchStrategies, fetchDeployments } =
    useStrategiesStore();
  const openNewStrategyDialog = useUIStore((s) => s.openNewStrategyDialog);
  const [params] = useSearchParams();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ListFilter>('all');
  const [requested, setRequested] = useState(false);
  const wide = useMediaQuery('(min-width: 1024px)');

  useEffect(() => {
    useStrategiesStore.setState({
      pageSize: PAGE_SIZE,
      page: 1,
      statusFilter: 'all',
      searchQuery: '',
    });
    setRequested(true);
    fetchStrategies().catch(() => undefined);
    fetchDeployments().catch(() => undefined);
  }, [fetchStrategies, fetchDeployments]);

  const rows = useMemo(
    () =>
      strategies.map((s) => {
        const state = runState(s, deployments[s.id]);
        return { strategy: s, state, label: stateLabel(state, deployments[s.id] !== undefined) };
      }),
    [strategies, deployments]
  );
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(
      (r) =>
        matchesFilter(r.state, filter) &&
        (!q ||
          r.strategy.name.toLowerCase().includes(q) ||
          r.strategy.symbols.some((sym) => sym.toLowerCase().includes(q)))
    );
  }, [rows, query, filter]);

  const running = rows.filter((r) => r.state === 'running').length;
  const selectedParam = params.get('s');
  const selectedId =
    shown.find((r) => r.strategy.id === selectedParam)?.strategy.id ??
    shown[0]?.strategy.id ??
    rows.find((r) => r.strategy.id === selectedParam)?.strategy.id ??
    null;
  const firstLoad = (!requested || loading) && strategies.length === 0;
  const clear = () => {
    setQuery('');
    setFilter('all');
  };

  if (!firstLoad && !error && strategies.length === 0) {
    return (
      <div className="page">
        <ListHeader count={null} running={0} onNew={openNewStrategyDialog} />
        <div className="mt-5">
          <StrategiesEmpty />
        </div>
      </div>
    );
  }

  const list = (
    <div className="flex min-h-0 flex-col">
      {firstLoad ? (
        <div aria-busy="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="grid grid-cols-[minmax(0,1fr)_64px_58px] items-center gap-3 border-t border-line px-[18px] py-3.5"
            >
              <span className="grid gap-1.5">
                <Skeleton className="h-3 w-36" />
                <Skeleton className="h-2.5 w-16" />
              </span>
              <Skeleton className="h-4 w-full" />
              <Skeleton className="ml-auto h-3 w-10" />
            </div>
          ))}
        </div>
      ) : error ? (
        <PanelError
          title="Strategies couldn’t be loaded"
          cause={error}
          onRetry={() => {
            fetchStrategies().catch(() => undefined);
          }}
        />
      ) : shown.length === 0 ? (
        <NoMatch
          noun="strategies"
          query={query}
          filters={
            filter === 'all' ? [] : [LIST_FILTERS.find((f) => f.key === filter)?.label ?? filter]
          }
          total={rows.length}
          onClear={clear}
        />
      ) : (
        shown.map((r) => (
          <StrategyListRow
            key={r.strategy.id}
            strategy={r.strategy}
            state={r.state}
            stateLabel={r.label}
            selected={wide && r.strategy.id === selectedId}
            to={wide ? `/strategies?s=${r.strategy.id}` : `/strategies/${r.strategy.id}`}
          />
        ))
      )}
      <p className="m-0 mt-auto border-t border-line px-4 py-3 text-[11.5px] text-fg-3 lg:px-[18px]">
        Curves and returns are from each strategy’s latest completed backtest.
      </p>
    </div>
  );

  const filters = (
    <div className="grid gap-3">
      <label className="flex h-9 items-center gap-2 rounded-[6px] border border-line-strong bg-panel px-3 focus-within:border-accent">
        <Search className="h-4 w-4 text-fg-3" aria-hidden="true" />
        <span className="sr-only">Search strategies and symbols</span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search strategies and symbols"
          className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-fg-3"
        />
      </label>
      <Segmented
        label="Show"
        options={LIST_FILTERS}
        value={filter}
        onChange={setFilter}
        className="justify-self-start"
      />
    </div>
  );

  if (!wide) {
    return (
      <div className="page relative isolate grid grid-cols-[minmax(0,1fr)] gap-4">
        <PageArt shape="own" />
        <ListHeader
          count={firstLoad ? undefined : total || rows.length}
          running={running}
          onNew={openNewStrategyDialog}
        />
        {filters}
        <div className="panel overflow-hidden [&>div>a:first-child]:border-t-0">{list}</div>
      </div>
    );
  }

  return (
    <div className="grid min-h-[calc(100vh-56px)] grid-cols-[340px_minmax(0,1fr)]">
      <aside className="flex flex-col border-r border-line bg-panel">
        <div className="grid gap-3 px-[18px] pb-3 pt-[18px]">
          <div className="flex items-center justify-between">
            <h1 className="m-0 text-[16px] font-semibold">Strategies</h1>
            <span className="flex gap-1.5">
              <Link to="/strategies/templates" className="btn btn-secondary btn-sm">
                Templates
              </Link>
              <button
                type="button"
                onClick={openNewStrategyDialog}
                className="btn btn-primary btn-sm px-2"
                aria-label="New strategy"
              >
                <Plus className="h-4 w-4" />
              </button>
            </span>
          </div>
          {!firstLoad && rows.length > 0 && (
            <p className="m-0 -mt-1.5 text-[12px] text-fg-3">
              {rows.length} {rows.length === 1 ? 'strategy' : 'strategies'} · {running} running in
              paper
            </p>
          )}
          {filters}
        </div>
        {list}
      </aside>
      <section className="min-w-0 px-7 py-[22px]">
        {selectedId ? (
          <SelectedOverview key={selectedId} id={selectedId} />
        ) : firstLoad ? (
          <SkeletonChart height={200} />
        ) : (
          <p className="m-0 mt-16 text-center text-[13px] text-fg-3">
            Clear the filters to pick a strategy.
          </p>
        )}
      </section>
    </div>
  );
}

function ListHeader({
  count,
  running,
  onNew,
}: {
  count: number | null | undefined;
  running: number;
  onNew: () => void;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="m-0 text-[22px] font-semibold tracking-[-0.015em]">Strategies</h1>
        <p className="m-0 mt-0.5 text-[12.5px] text-fg-3">
          {count === undefined
            ? '\u00a0'
            : count === null
              ? 'No strategies yet'
              : `${count} ${count === 1 ? 'strategy' : 'strategies'} · ${running} running in paper`}
        </p>
      </div>
      <div className="flex gap-2">
        <Link to="/strategies/templates" className="btn btn-secondary">
          Templates
        </Link>
        <button type="button" onClick={onNew} className="btn btn-primary">
          <Plus className="h-4 w-4" />
          New strategy
        </button>
      </div>
    </div>
  );
}
