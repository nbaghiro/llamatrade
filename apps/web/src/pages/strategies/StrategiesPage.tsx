import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { Plus, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { LaneLegend } from '../../components/charts';
import { DeploySheet } from '../../components/sessions/DeploySheet';
import { etToday } from '../../components/sessions/sessionRows';
import { useSessionRows } from '../../components/shell/useSessionRows';
import { stageRow, trackSummary } from '../../components/strategies/stageModel';
import {
  StageTrackHead,
  StageTrackPhoneRow,
  StageTrackRow,
} from '../../components/strategies/StageTrackTable';
import { StrategiesEmpty } from '../../components/strategies/StrategiesEmpty';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { NoMatch, PageArt, PageHead, PanelError, Skeleton } from '../../components/ui';
import { useUIStore } from '../../store/ui';

const PAGE_SIZE = 100;

export default function StrategiesPage() {
  const { strategies, loading, error, fetchStrategies } = useStrategiesStore();
  const openNewStrategyDialog = useUIStore((s) => s.openNewStrategyDialog);
  const sessions = useSessionRows();
  const [query, setQuery] = useState('');
  const [requested, setRequested] = useState(false);
  const [deploying, setDeploying] = useState<Strategy | null>(null);
  const wide = useMediaQuery('(min-width: 1024px)');
  const today = useMemo(() => etToday(), []);

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

  const summary = useMemo(
    () => trackSummary(strategies.map((s) => stageRow(s, null, sessions, today))),
    [strategies, sessions, today]
  );

  const firstLoad = (!requested || loading) && strategies.length === 0;

  if (!firstLoad && !error && strategies.length === 0) {
    return (
      <div className="page relative isolate">
        <PageArt shape="build" />
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

  const Row = wide ? StageTrackRow : StageTrackPhoneRow;

  return (
    <div className="page relative isolate">
      <PageArt shape="own" />
      <PageHead
        title="Strategies"
        sub={firstLoad ? ' ' : summary}
        actions={
          <>
            {search}
            <Link to="/strategies/templates" className="btn btn-secondary">
              Templates
            </Link>
            <button type="button" onClick={openNewStrategyDialog} className="btn btn-primary">
              <Plus className="h-4 w-4" />
              New strategy
            </button>
          </>
        }
      />

      <section className="panel-rim overflow-hidden" aria-label="Strategies by stage">
        <div role="table" aria-label="Strategies by stage">
          {wide && <StageTrackHead />}
          {firstLoad ? (
            <div aria-busy="true">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="grid gap-2 border-t border-line px-5 py-4 first:border-t-0">
                  <Skeleton className="h-3 w-40" />
                  <Skeleton className="h-2.5 w-full" />
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
              filters={[]}
              total={strategies.length}
              onClear={() => setQuery('')}
            />
          ) : (
            <div className="[&>div:first-child]:border-t-0">
              {shown.map((s) => (
                <Row
                  key={s.id}
                  strategy={s}
                  sessions={sessions}
                  today={today}
                  onDeploy={setDeploying}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[12px] text-fg-3">
        <p className="m-0 max-w-[760px]">
          Backtested shows each strategy’s latest completed backtest against its benchmark. Paper
          and Live show the session’s value on Alpaca.
        </p>
        <LaneLegend
          items={[
            { shape: 'dot', label: 'Current stage' },
            { shape: 'planned', label: 'Next step' },
          ]}
        />
      </div>

      {deploying && (
        <DeploySheet
          open
          onClose={() => setDeploying(null)}
          strategyId={deploying.id}
          strategyName={deploying.name}
          strategyVersion={deploying.version}
          rebalance={deploying.rebalance || undefined}
        />
      )}
    </div>
  );
}
