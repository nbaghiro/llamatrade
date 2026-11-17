import { toDate } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { Pencil } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { DeploySheet } from '../../components/sessions/DeploySheet';
import { dayLabel, etToday } from '../../components/sessions/sessionRows';
import { HoldTodayTab } from '../../components/strategies/detail/HoldTodayTab';
import { OverviewTab } from '../../components/strategies/detail/OverviewTab';
import { PerformanceTab } from '../../components/strategies/detail/PerformanceTab';
import { RulesTab } from '../../components/strategies/detail/RulesTab';
import { toTab, TABS, type DetailTab } from '../../components/strategies/detail/tabs';
import { useFullRun, useStrategyRuns } from '../../components/strategies/detail/useRuns';
import { useStrategySession } from '../../components/strategies/detail/useStrategySession';
import { VersionsTab } from '../../components/strategies/detail/VersionsTab';
import { pickSameDatesRun } from '../../components/strategies/sameDates';
import { useStrategyDetail } from '../../components/strategies/useStrategyDetail';
import { useVersions } from '../../components/strategies/versions/useVersions';
import {
  AttentionLine,
  EmptyState,
  ModeBadge,
  PageArt,
  PageHead,
  PanelError,
  Skeleton,
  SkeletonChart,
  StatusMark,
  Tabs,
  WebOnlyNote,
} from '../../components/ui';
import { rebalanceWord } from '../../lib/outline';

export default function StrategyDetailPage({ tab: fixedTab }: { tab?: DetailTab }) {
  const { id = '', tab: tabParam } = useParams<{ id: string; tab?: string }>();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const tab = fixedTab ?? toTab(tabParam ?? params.get('tab'));
  const detail = useStrategyDetail(id);
  const ss = useStrategySession(id);
  const { runs, loading: runsLoading } = useStrategyRuns(id);
  const versions = useVersions(id);
  const [deploying, setDeploying] = useState(false);

  const row = ss.row;
  const sessionVersion = detail.session.version ?? (row?.version || null);
  const startedAt = row?.startedAt ?? null;
  const endDay = Math.floor((toDate(row?.session.endedAt) ?? new Date()).getTime() / 86_400_000);
  const sameMeta = useMemo(
    () =>
      startedAt
        ? pickSameDatesRun(runs, startedAt, new Date((endDay + 1) * 86_400_000), sessionVersion)
        : null,
    [runs, startedAt, endDay, sessionVersion]
  );
  const sameRun = useFullRun(sameMeta?.id);

  const strategy = detail.strategy;
  const crumbs = [{ label: 'Strategies', to: '/strategies' }, { label: strategy?.name ?? '' }];

  if (!strategy) {
    return (
      <div className="page">
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
            <Skeleton className="h-3 w-40" />
            <Skeleton className="h-7 w-64" />
            <SkeletonChart height={240} />
          </div>
        )}
      </div>
    );
  }

  const parsed = fromDSLString(strategy.dslCode);
  const rebalance = parsed?.metadata.timeframe
    ? rebalanceWord(parsed.metadata.timeframe)
    : strategy.rebalance;
  const benchmark = parsed?.metadata.benchmark;
  const latest = versions.state.status === 'ready' ? versions.state.versions[0] : undefined;
  const latestAt = toDate(latest?.createdAt);
  const behind = sessionVersion !== null && strategy.version > sessionVersion;
  const sub = [
    rebalance ? `${rebalance[0].toUpperCase()}${rebalance.slice(1)} rebalance` : '',
    benchmark ? `benchmark ${benchmark}` : '',
    behind
      ? `version ${strategy.version} saved${latestAt ? ` ${dayLabel(etToday(latestAt))}` : ''} and not in the session yet`
      : `version ${strategy.version || 1}`,
  ]
    .filter(Boolean)
    .join(' · ');

  const live = row?.session.mode === ExecutionMode.LIVE;
  const badges = (
    <>
      {row && <ModeBadge mode={live ? 'live' : 'paper'} size="sm" />}
      <StatusMark
        state={detail.state}
        label={
          row && row.view.open && sessionVersion
            ? `${row.view.label} on version ${sessionVersion}`
            : detail.stateLabel
        }
      />
    </>
  );

  const attention =
    detail.state === 'error' ? (
      <AttentionLine
        items={[
          {
            id: 'error',
            title: 'The session stopped with an error.',
            detail: 'Nothing trades for this strategy until the session is looked at.',
            action: row ? (
              <Link to={`/trading/${row.session.id}`} className="btn btn-secondary btn-sm">
                Review
              </Link>
            ) : undefined,
          },
        ]}
      />
    ) : undefined;

  return (
    <div className="page relative isolate">
      <PageArt shape="own" />
      <PageHead
        crumbs={crumbs}
        title={strategy.name}
        badges={badges}
        sub={sub}
        attention={attention}
        actions={
          <>
            <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-secondary">
              Backtest
            </Link>
            {row && (
              <Link to={`/trading/${row.session.id}`} className="btn btn-secondary">
                Open session
              </Link>
            )}
            <Link to={`/strategies/${strategy.id}/edit`} className="btn btn-primary max-md:hidden">
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Link>
          </>
        }
      />
      <div className="mb-3 md:hidden">
        <WebOnlyNote what="Editing strategies" />
      </div>
      <Tabs
        label="Strategy sections"
        options={TABS.map((t) => ({
          key: t.key,
          label: <span className="whitespace-nowrap">{t.label}</span>,
        }))}
        value={tab}
        onChange={(k) =>
          navigate(k === 'overview' ? `/strategies/${id}` : `/strategies/${id}/${k}`, {
            replace: true,
          })
        }
        className="no-scrollbar mb-5 overflow-x-auto"
      />

      {!ss.loaded && tab !== 'rules' ? <SkeletonChart height={240} /> : null}
      {ss.loaded && tab === 'overview' && (
        <OverviewTab
          strategy={strategy}
          ss={ss}
          running={detail.session}
          latestRun={detail.run}
          sameRun={sameMeta ? sameRun : null}
          versions={versions.state.status === 'ready' ? versions.state.versions : []}
          onDeploy={() => setDeploying(true)}
        />
      )}
      {ss.loaded && tab === 'today' && (
        <HoldTodayTab strategy={strategy} ss={ss} running={detail.session} />
      )}
      {tab === 'rules' && <RulesTab strategy={strategy} runs={runs} />}
      {ss.loaded && tab === 'performance' && (
        <PerformanceTab
          strategy={strategy}
          ss={ss}
          sameRun={sameMeta ? sameRun : null}
          runs={runs}
          runsLoading={runsLoading}
        />
      )}
      {ss.loaded && tab === 'versions' && (
        <VersionsTab
          strategy={strategy}
          ss={ss}
          sessionVersion={sessionVersion}
          runs={runs}
          source={versions}
          onDeploy={() => setDeploying(true)}
        />
      )}

      <DeploySheet
        open={deploying}
        onClose={() => setDeploying(false)}
        strategyId={strategy.id}
        strategyName={strategy.name}
        strategyVersion={strategy.version}
        rebalance={strategy.rebalance || undefined}
      />
    </div>
  );
}
