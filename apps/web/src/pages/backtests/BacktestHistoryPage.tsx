import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { AlertTriangle, Columns2, FlaskConical, Plus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { compareColor } from '../../components/backtest/compareColors';
import { newerThanTrading } from '../../components/backtest/historyLanes';
import { runDay } from '../../components/backtest/historyLanes';
import { HistoryTable } from '../../components/backtest/HistoryTable';
import { inFlight, strategyRows } from '../../components/backtest/historyTimeline';
import { LaneRunTable, NewerCallout } from '../../components/backtest/LaneRuns';
import { LatestRunCard } from '../../components/backtest/LatestRunCard';
import { Panel, RunStatus } from '../../components/backtest/parts';
import { phaseOf } from '../../components/backtest/runData';
import { strategyNameOf } from '../../components/backtest/runLabels';
import { RunningStrip } from '../../components/backtest/RunningStrip';
import { latestSession, sessionForVersion } from '../../components/backtest/strategySessions';
import { StrategyTimeline } from '../../components/backtest/StrategyTimeline';
import { useStrategySessions } from '../../components/backtest/useStrategySessions';
import { EmptyState, NoMatch } from '../../components/ui/EmptyState';
import { Pct } from '../../components/ui/Num';
import { PageHead } from '../../components/ui/PageHead';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonRows } from '../../components/ui/Skeleton';
import { Segmented } from '../../components/ui/Tabs';
import { asFrequency, COMPARE_SOFT_LIMIT, longDate, parseRunIds } from '../../lib/backtestView';
import { formatNumber, formatPct } from '../../lib/format';

type StateFilter = 'all' | 'completed' | 'other';
const PAGE = 50;
const LANES = 8;

/** The range every selected run covers, from their configs. */
function sharedRange(runs: readonly BacktestRun[]): { start: Date; end: Date } | null {
  let start = -Infinity;
  let end = Infinity;
  for (const r of runs) {
    const a = toDate(r.config?.startDate);
    const b = toDate(r.config?.endDate);
    if (!a || !b) return null;
    start = Math.max(start, a.getTime());
    end = Math.min(end, b.getTime());
  }
  return runs.length && start < end ? { start: new Date(start), end: new Date(end) } : null;
}

/** /backtests: every run newest first; ticking completed runs fills a compare tray. */
export default function BacktestHistoryPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const history = useBacktestStore((s) => s.history);
  const loadHistory = useBacktestStore((s) => s.loadHistory);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const [pageSize, setPageSize] = useState(PAGE);
  const [state, setState] = useState<StateFilter>('all');
  const [strategyId, setStrategyId] = useState('');
  const [selected, setSelected] = useState<string[]>(() => parseRunIds(params.get('select')));
  const fetchLatest = useBacktestStore((s) => s.fetchLatestCompletedBacktest);
  const [latestRun, setLatestRun] = useState<BacktestRun | null>(null);
  const [showAllLanes, setShowAllLanes] = useState(false);
  const { sessions } = useStrategySessions();

  useEffect(() => {
    fetchStrategies().catch(() => undefined);
  }, [fetchStrategies]);

  useEffect(() => {
    loadHistory(1, pageSize).catch(() => undefined);
  }, [loadHistory, pageSize]);

  const runs = useMemo(
    () =>
      history.runs.filter(
        (r) =>
          (!strategyId || r.strategyId === strategyId) &&
          (state === 'all' || (state === 'completed') === (r.status === BacktestStatus.COMPLETED))
      ),
    [history.runs, strategyId, state]
  );
  const strategyCount = new Set(history.runs.map((r) => r.strategyId)).size;
  const rows = useMemo(() => strategyRows(history.runs), [history.runs]);
  const running = useMemo(() => inFlight(history.runs), [history.runs]);
  const newestDone = useMemo(
    () =>
      rows
        .map((r) => r.latestCompleted)
        .filter((r) => r !== null)
        .sort((a, b) => b.at.getTime() - a.at.getTime())[0]?.run ?? null,
    [rows]
  );
  const newestDoneId = newestDone?.id ?? '';
  const newestStrategy = newestDone?.strategyId ?? '';

  useEffect(() => {
    if (!newestStrategy) return;
    let live = true;
    fetchLatest(newestStrategy)
      .then((r) => {
        if (live) setLatestRun(r && r.id === newestDoneId ? r : null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [fetchLatest, newestStrategy, newestDoneId]);

  const laneRow = strategyId ? (rows.find((r) => r.strategyId === strategyId) ?? null) : null;
  const newer = laneRow ? newerThanTrading(laneRow, sessions, history.metrics) : null;
  const laneName = strategyNameOf(strategies, strategyId);
  const earlier = runs.filter((r) => r.id !== latestRun?.id);
  const picked = history.runs.filter((r) => selected.includes(r.id));
  const range = sharedRange(picked);
  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const filtered = state !== 'all' || strategyId !== '';

  const filters = (
    <>
      <Segmented<StateFilter>
        label="Run state"
        value={state}
        onChange={setState}
        options={[
          { key: 'all', label: 'All' },
          { key: 'completed', label: 'Completed' },
          { key: 'other', label: 'Not completed' },
        ]}
      />
      <select
        aria-label="Strategy"
        className="select h-8 w-[180px]"
        value={strategyId}
        onChange={(e) => setStrategyId(e.target.value)}
      >
        <option value="">All strategies</option>
        {strategies.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </>
  );

  let body;
  if (history.error && !history.runs.length) {
    body = (
      <PanelError
        title="Backtests couldn't be loaded"
        cause={history.error}
        onRetry={() => loadHistory(1, pageSize)}
        retrying={history.loading}
      />
    );
  } else if (!history.loaded) {
    body = <SkeletonRows rows={8} cols={6} />;
  } else if (!history.runs.length) {
    body = (
      <EmptyState
        icon={FlaskConical}
        title="No backtests yet"
        body="Run a strategy over history to see how it would have done. Every run is listed here, including failed and cancelled ones."
        actions={
          <Link to="/backtest" className="btn btn-primary">
            Set up a run
          </Link>
        }
      />
    );
  } else if (!runs.length) {
    body = (
      <NoMatch
        noun="runs"
        filters={[
          ...(state === 'completed' ? ['Completed'] : state === 'other' ? ['Not completed'] : []),
          ...(strategyId ? [strategyNameOf(strategies, strategyId)] : []),
        ]}
        total={history.runs.length}
        onClear={() => {
          setState('all');
          setStrategyId('');
        }}
      />
    );
  } else {
    body = (
      <>
        <div className="hidden md:block">
          {laneRow ? (
            <LaneRunTable
              runs={runs}
              metrics={history.metrics}
              session={latestSession(sessions, strategyId)}
            />
          ) : (
            <HistoryTable
              runs={runs}
              metrics={history.metrics}
              strategies={strategies}
              selected={selected}
              onToggle={toggle}
            />
          )}
        </div>
        <ul className="m-0 list-none p-0 md:hidden">
          {earlier.map((r) => {
            const done = r.status === BacktestStatus.COMPLETED;
            const m = history.metrics[r.id];
            return (
              <li key={r.id} className="border-b border-line last:border-b-0">
                <Link
                  to={done ? `/backtest/${r.id}` : `/backtest?run=${r.id}`}
                  className="flex items-center justify-between gap-3 px-4 py-3"
                >
                  <span className="grid min-w-0 gap-px">
                    <span className="truncate text-sm">
                      {strategyNameOf(strategies, r.strategyId)}{' '}
                      <span className="text-fg-3">v{r.strategyVersion}</span>
                    </span>
                    <span className="num truncate text-[11.5px] text-fg-3">
                      {runDay(r)}
                      {done && m
                        ? ` · Sharpe ${formatNumber(toNumber(m.sharpeRatio), { dp: 2 })} · Worst ${formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1 })}`
                        : ''}
                    </span>
                  </span>
                  {done && m ? (
                    <Pct value={toNumber(m.totalReturn)} pnl dp={1} />
                  ) : (
                    <RunStatus phase={phaseOf(r.status)} />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </>
    );
  }

  return (
    <div className="page grid gap-3.5 pb-28">
      <PageHead
        title="Backtests"
        sub={
          history.loaded && history.runs.length
            ? `${history.total} ${history.total === 1 ? 'run' : 'runs'} across ${strategyCount} ${strategyCount === 1 ? 'strategy' : 'strategies'}${running.length ? ` · ${running.length} running` : ''} · every result on this page is a backtest`
            : undefined
        }
        actions={
          <Link to="/backtest" className="btn btn-primary">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            New backtest
          </Link>
        }
      />
      {running.map((r) => (
        <RunningStrip
          key={r.id}
          run={r}
          strategyName={strategyNameOf(strategies, r.strategyId)}
          rebalance={asFrequency(strategies.find((s) => s.id === r.strategyId)?.rebalance)}
        />
      ))}
      {latestRun && (
        <div className="md:hidden">
          <LatestRunCard
            run={latestRun}
            strategyName={strategyNameOf(strategies, latestRun.strategyId)}
            session={sessionForVersion(sessions, latestRun.strategyId, latestRun.strategyVersion)}
          />
        </div>
      )}
      {rows.length > 0 && (
        <section className="panel-rim hidden min-w-0 overflow-hidden md:block">
          <StrategyTimeline
            rows={showAllLanes ? rows : rows.slice(0, LANES)}
            metrics={history.metrics}
            strategies={strategies}
            selected={strategyId}
            onSelect={setStrategyId}
            today={new Date()}
            sessions={sessions}
          />
          {rows.length > LANES && (
            <button
              type="button"
              className="w-full border-t border-line px-3.5 py-2 text-left text-[12px] text-accent hover:underline"
              onClick={() => setShowAllLanes((v) => !v)}
            >
              {showAllLanes ? 'Show fewer strategies' : `Show all ${rows.length} strategies`}
            </button>
          )}
        </section>
      )}
      <div
        className={newer ? 'grid gap-3.5 md:grid-cols-[minmax(0,1fr)_300px] md:items-start' : ''}
      >
        <Panel
          title={
            <>
              <span className="md:hidden">Earlier</span>
              <span className="hidden md:inline">
                {strategyId
                  ? `${laneName} · ${runs.length} ${runs.length === 1 ? 'run' : 'runs'}`
                  : 'All runs'}
              </span>
            </>
          }
          aside={
            <>
              <span className="text-[11.5px] text-fg-3 md:hidden">Newest first</span>
              <span className="hidden flex-wrap items-center gap-2 md:flex">
                {laneRow ? (
                  <>
                    <span className="text-[11.5px] text-fg-3">Newest first ·</span>
                    <button
                      type="button"
                      className="text-[11.5px] text-accent hover:underline"
                      onClick={() => setStrategyId('')}
                    >
                      Show all {history.runs.length}
                    </button>
                  </>
                ) : (
                  filters
                )}
              </span>
            </>
          }
          footer={
            history.runs.length > 0 ? (
              <span className="flex items-center justify-between gap-3">
                <span>
                  {filtered ? `${runs.length} shown of ` : ''}
                  {history.runs.length} of {history.total} runs
                </span>
                {history.runs.length < history.total && (
                  <button
                    type="button"
                    className="text-accent hover:underline disabled:opacity-50"
                    disabled={history.loading}
                    onClick={() => setPageSize((n) => n + PAGE)}
                  >
                    Show more
                  </button>
                )}
              </span>
            ) : undefined
          }
        >
          {body}
        </Panel>
        {newer && (
          <div className="hidden md:block">
            <NewerCallout newer={newer} name={laneName} />
          </div>
        )}
      </div>

      {selected.length > 0 && (
        <div
          role="region"
          aria-label="Compare tray"
          className="fixed inset-x-4 bottom-[96px] z-30 mx-auto flex max-w-[760px] flex-wrap items-center gap-3 rounded-[8px] border border-line-strong bg-panel px-4 py-2.5 text-[12.5px] shadow-xl md:bottom-6"
        >
          <span className="flex gap-1" aria-hidden="true">
            {selected.slice(0, 5).map((id, i) => (
              <i
                key={id}
                className="block h-2 w-2 rounded-[2px]"
                style={{ background: compareColor(i) }}
              />
            ))}
          </span>
          <span className="min-w-0 flex-1">
            <b className="font-semibold">
              {selected.length} {selected.length === 1 ? 'run' : 'runs'} selected
            </b>
            <span className="text-fg-3">
              {selected.length < 2
                ? ' · pick one more to compare'
                : range
                  ? `, compared over ${longDate(range.start)} to ${longDate(range.end)}`
                  : ' · these runs share no dates'}
            </span>
            {selected.length > COMPARE_SOFT_LIMIT && (
              <span className="mt-0.5 flex items-center gap-1 text-risk">
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                More than {COMPARE_SOFT_LIMIT} lines get hard to read on one chart.
              </span>
            )}
          </span>
          <button type="button" className="btn btn-secondary" onClick={() => setSelected([])}>
            Clear
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={selected.length < 2 || !range}
            onClick={() => navigate(`/backtests/compare?runs=${selected.join(',')}`)}
          >
            <Columns2 className="h-3.5 w-3.5" aria-hidden="true" />
            Compare
          </button>
        </div>
      )}
    </div>
  );
}
