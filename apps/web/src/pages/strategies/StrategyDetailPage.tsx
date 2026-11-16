import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { ArrowLeft } from 'lucide-react';
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { DeploySheet } from '../../components/sessions/DeploySheet';
import { StrategyHeader, StrategyOverviewBody } from '../../components/strategies/StrategyOverview';
import {
  dayMonthYear,
  newestFirst,
  rangeLabel,
  runFigures,
  summaryLine,
} from '../../components/strategies/strategyView';
import { useStrategyDetail } from '../../components/strategies/useStrategyDetail';
import { VersionsView } from '../../components/strategies/versions/VersionsView';
import type { RunningSession } from '../../components/strategy-builder/hooks/useRunningSession';
import { Outline, Parts } from '../../components/strategy-builder/outline/Outline';
import {
  EmptyState,
  PanelError,
  Pct,
  Segmented,
  Skeleton,
  SkeletonChart,
  SkeletonRows,
  Tabs,
} from '../../components/ui';
import { buildOutline, metaParts } from '../../lib/outline';

const DslCodeBlock = lazy(() => import('../../components/strategies/DslCodeBlock'));

export type DetailTab = 'overview' | 'definition' | 'backtests' | 'versions' | 'session';
const TAB_KEYS: readonly DetailTab[] = [
  'overview',
  'definition',
  'backtests',
  'versions',
  'session',
];

const isTab = (v: string | null | undefined): v is DetailTab =>
  !!v && (TAB_KEYS as readonly string[]).includes(v);

const STATUS_WORD: Record<BacktestStatus, string> = {
  [BacktestStatus.UNSPECIFIED]: 'Unknown',
  [BacktestStatus.PENDING]: 'Queued',
  [BacktestStatus.RUNNING]: 'Running',
  [BacktestStatus.COMPLETED]: 'Completed',
  [BacktestStatus.FAILED]: 'Failed',
  [BacktestStatus.CANCELLED]: 'Cancelled',
};

function Definition({ strategy }: { strategy: Strategy }) {
  const [view, setView] = useState<'outline' | 'code'>('outline');
  const parsed = useMemo(() => fromDSLString(strategy.dslCode), [strategy.dslCode]);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Definition view"
          options={[
            { key: 'outline', label: 'Outline' },
            { key: 'code', label: 'Code' },
          ]}
          value={view}
          onChange={setView}
        />
        <Link to={`/strategies/${strategy.id}/edit`} className="btn btn-secondary btn-sm">
          Edit
        </Link>
      </div>
      {view === 'code' || !parsed ? (
        <Suspense fallback={<Skeleton className="h-48 w-full" />}>
          <DslCodeBlock code={strategy.dslCode} className="rounded-panel border border-line" />
        </Suspense>
      ) : (
        <div className="max-w-[860px]">
          <p className="m-0 mb-4 text-[13.5px] text-fg-2">
            <Parts
              parts={metaParts({
                timeframe: parsed.metadata.timeframe ?? '1D',
                benchmark: parsed.metadata.benchmark ?? '',
              })}
            />
          </p>
          <Outline lines={buildOutline(parsed.tree)} label={`${strategy.name} outline`} />
        </div>
      )}
    </div>
  );
}

function Backtests({
  strategy,
  runs,
  loading,
}: {
  strategy: Strategy;
  runs: BacktestRun[];
  loading: boolean;
}) {
  if (loading && runs.length === 0) {
    return (
      <div className="panel">
        <SkeletonRows rows={4} cols={4} />
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <div className="panel">
        <EmptyState
          title="No backtests yet"
          body="A backtest shows how this strategy would have done before anything runs."
          actions={
            <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-primary">
              Run a backtest
            </Link>
          }
        />
      </div>
    );
  }
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-[11.5px] text-fg-3">
            <th className="px-4 py-2.5 font-medium">Run</th>
            <th className="px-4 py-2.5 font-medium">Version</th>
            <th className="px-4 py-2.5 font-medium">Range</th>
            <th className="px-4 py-2.5 font-medium">State</th>
            <th className="px-4 py-2.5 text-right font-medium">Return</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const when = toDate(r.completedAt) ?? toDate(r.createdAt);
            const f = runFigures(r);
            const total = r.results?.metrics ? num(r.results.metrics.totalReturn) : null;
            const failed = r.status === BacktestStatus.FAILED;
            return (
              <tr key={r.id} className="border-t border-line hover:bg-sunk/60">
                <td className="px-4 py-2.5">
                  <Link
                    to={`/backtest/${r.id}`}
                    className="text-fg hover:text-accent hover:underline"
                  >
                    {when ? dayMonthYear(when) : r.id.slice(0, 8)}
                  </Link>
                </td>
                <td className="num px-4 py-2.5 text-fg-2">{r.strategyVersion || ''}</td>
                <td className="px-4 py-2.5 text-fg-2">{f ? rangeLabel(f) : ''}</td>
                <td className={`px-4 py-2.5 ${failed ? 'text-risk' : 'text-fg-2'}`}>
                  {STATUS_WORD[r.status]}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {total === null ? '' : <Pct value={total} pnl dp={1} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Session({ strategy, session }: { strategy: Strategy; session: RunningSession }) {
  const [deployOpen, setDeployOpen] = useState(false);
  if (session.loading) {
    return <Skeleton className="h-24 w-full" />;
  }
  if (!session.session) {
    return (
      <div className="panel">
        <EmptyState
          title="Not running in paper"
          body="Deploy a saved version to paper to run it on live prices without real money."
          actions={
            <button type="button" onClick={() => setDeployOpen(true)} className="btn btn-primary">
              Deploy to paper
            </button>
          }
        />
        <DeploySheet
          open={deployOpen}
          onClose={() => setDeployOpen(false)}
          strategyId={strategy.id}
          strategyName={strategy.name}
          strategyVersion={strategy.version}
          rebalance={strategy.rebalance || undefined}
        />
      </div>
    );
  }
  const started = toDate(session.session.startedAt);
  return (
    <div className="panel grid gap-3 px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <b className="text-[14px] font-semibold">{session.session.name || 'Paper session'}</b>
          <p className="m-0 mt-0.5 text-[12px] text-fg-3">
            Paper
            {session.version ? ` · runs version ${session.version}` : ''}
            {started ? ` · since ${dayMonthYear(started)}` : ''}
          </p>
        </div>
        <Link to={`/trading/${session.session.id}`} className="btn btn-secondary">
          Open session
        </Link>
      </div>
      <p className="m-0 text-[12.5px] text-fg-2">
        The session keeps running its exact version until you redeploy a newer one.
      </p>
    </div>
  );
}

export default function StrategyDetailPage() {
  const { id = '', tab: tabParam } = useParams<{ id: string; tab?: string }>();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryTab = params.get('tab');
  const tab: DetailTab = isTab(tabParam) ? tabParam : isTab(queryTab) ? queryTab : 'overview';
  const detail = useStrategyDetail(id);

  const backtests = useBacktestStore((s) => s.backtests);
  const backtestsLoading = useBacktestStore((s) => s.loading);
  const listBacktests = useBacktestStore((s) => s.listBacktests);
  useEffect(() => {
    listBacktests(id).catch(() => undefined);
  }, [id, listBacktests]);
  const runs = useMemo(
    () => newestFirst(backtests.filter((b) => b.strategyId === id)),
    [backtests, id]
  );

  const versions = detail.strategy?.version ?? 0;
  const options = [
    { key: 'overview' as const, label: 'Overview' },
    { key: 'definition' as const, label: 'Definition' },
    {
      key: 'backtests' as const,
      label: (
        <>
          Backtests
          <em className="ml-1 font-mono text-[11px] not-italic text-fg-3">{runs.length || ''}</em>
        </>
      ),
    },
    {
      key: 'versions' as const,
      label: (
        <>
          Versions
          <em className="ml-1 font-mono text-[11px] not-italic text-fg-3">{versions || ''}</em>
        </>
      ),
    },
    { key: 'session' as const, label: 'Session' },
  ];

  const back = (
    <Link
      to="/strategies"
      className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      Strategies
    </Link>
  );

  if (!detail.strategy) {
    return (
      <div className="page grid grid-cols-[minmax(0,1fr)] gap-4">
        {back}
        {detail.status === 'missing' ? (
          <EmptyState
            title="This strategy doesn’t exist"
            body="It may have been deleted. Your other strategies are on the list."
            actions={
              <Link to="/strategies" className="btn btn-secondary">
                Back to strategies
              </Link>
            }
          />
        ) : detail.status === 'error' ? (
          <PanelError title="This strategy couldn’t be loaded" onRetry={detail.retry} />
        ) : (
          <div className="grid gap-4" aria-busy="true">
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-3 w-80" />
            <SkeletonChart height={130} />
          </div>
        )}
      </div>
    );
  }

  const strategy = detail.strategy;
  return (
    <div className="page grid grid-cols-[minmax(0,1fr)] gap-4">
      {back}
      <StrategyHeader
        strategy={strategy}
        state={detail.state}
        stateLabel={detail.stateLabel}
        meta={detail.meta}
        headingLevel="h1"
      />
      <Tabs
        label="Strategy sections"
        options={options}
        value={tab}
        onChange={(k) =>
          navigate(k === 'overview' ? `/strategies/${id}` : `/strategies/${id}/${k}`, {
            replace: true,
          })
        }
        className="no-scrollbar overflow-x-auto"
      />
      {tab === 'overview' && (
        <>
          {summaryLine(strategy) && (
            <p className="-mt-1 m-0 text-[13.5px] text-fg-2">{summaryLine(strategy)}</p>
          )}
          <StrategyOverviewBody
            strategy={strategy}
            state={detail.state}
            run={detail.run}
            session={detail.session}
          />
        </>
      )}
      {tab === 'definition' && <Definition strategy={strategy} />}
      {tab === 'backtests' && (
        <Backtests strategy={strategy} runs={runs} loading={backtestsLoading} />
      )}
      {tab === 'versions' && (
        <VersionsView
          strategyId={id}
          strategyName={strategy.name}
          sessionVersion={detail.session.version}
        />
      )}
      {tab === 'session' && <Session strategy={strategy} session={detail.session} />}
    </div>
  );
}
