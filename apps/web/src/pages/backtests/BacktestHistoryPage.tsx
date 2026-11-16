import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { AlertTriangle, Columns2, FlaskConical, Plus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { compareColor } from '../../components/backtest/compareColors';
import { HistoryTable } from '../../components/backtest/HistoryTable';
import { PageHead, Panel, RunStatus } from '../../components/backtest/parts';
import { phaseOf } from '../../components/backtest/runData';
import { runWhen, strategyNameOf } from '../../components/backtest/runLabels';
import { EmptyState, NoMatch } from '../../components/ui/EmptyState';
import { Pct } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonRows } from '../../components/ui/Skeleton';
import { Segmented } from '../../components/ui/Tabs';
import { COMPARE_SOFT_LIMIT, longDate, parseRunIds } from '../../lib/backtestView';

type StateFilter = 'all' | 'completed' | 'other';
const PAGE = 50;

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
      <Link to="/backtest" className="btn btn-primary">
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        New backtest
      </Link>
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
          <HistoryTable
            runs={runs}
            metrics={history.metrics}
            strategies={strategies}
            selected={selected}
            onToggle={toggle}
          />
        </div>
        <ul className="m-0 list-none p-0 md:hidden">
          {runs.map((r) => {
            const done = r.status === BacktestStatus.COMPLETED;
            const on = selected.includes(r.id);
            const m = history.metrics[r.id];
            return (
              <li
                key={r.id}
                className={`flex items-center justify-between gap-3 border-b border-line px-4 py-3 last:border-b-0 ${on ? 'bg-accent-soft' : ''}`}
              >
                <span className="flex min-w-0 items-center gap-2.5">
                  {done ? (
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => toggle(r.id)}
                      aria-label={`Compare ${strategyNameOf(strategies, r.strategyId)}`}
                      className="h-4 w-4 accent-[rgb(var(--accent-fill))]"
                    />
                  ) : (
                    <span className="w-4" />
                  )}
                  <Link to={`/backtest/${r.id}`} className="grid min-w-0 gap-px">
                    <span className="truncate text-sm">
                      {strategyNameOf(strategies, r.strategyId)}{' '}
                      <span className="text-fg-3">v{r.strategyVersion}</span>
                    </span>
                    <span className="num text-[11.5px] text-fg-3">{runWhen(r)}</span>
                  </Link>
                </span>
                {done && m ? (
                  <Pct value={toNumber(m.totalReturn)} pnl dp={1} />
                ) : (
                  <RunStatus phase={phaseOf(r.status)} />
                )}
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
        title="Backtest history"
        meta={
          history.loaded && history.runs.length
            ? `${history.total} runs · ${strategyCount} ${strategyCount === 1 ? 'strategy' : 'strategies'}`
            : undefined
        }
        actions={filters}
      />
      <Panel
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
