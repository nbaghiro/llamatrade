import { toDate } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { StrategyVersion } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { ChevronLeft, Pencil, Play } from 'lucide-react';
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
import { sentenceText, summaryParts } from '../../components/strategies/rules/ruleSentence';
import { RuleSentenceView } from '../../components/strategies/rules/RuleSentenceView';
import { useRulesModel } from '../../components/strategies/rules/useRulesModel';
import { pickSameDatesRun } from '../../components/strategies/sameDates';
import { useStrategyDetail } from '../../components/strategies/useStrategyDetail';
import { useVersions } from '../../components/strategies/versions/useVersions';
import {
  AttentionLine,
  EmptyState,
  ModeBadge,
  PanelError,
  Skeleton,
  SkeletonChart,
  StatusMark,
} from '../../components/ui';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { rebalanceWord } from '../../lib/outline';

const NO_VERSIONS: readonly StrategyVersion[] = [];

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
  const model = useRulesModel(
    strategy ?? null,
    versions.state.status === 'ready' ? versions.state.versions : NO_VERSIONS,
    runs
  );
  useDocumentTitle(strategy?.name);

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

  const summary = model.sentence ? summaryParts(model.sentence) : null;
  const subLine =
    tab === 'overview' && summary && summary.length > 0 ? (
      <div className="min-w-0 truncate text-[13px] text-fg-2" title={sentenceText(summary)}>
        <span>Version {strategy.version || 1} · </span>
        <RuleSentenceView
          parts={summary}
          href={(t) => `/strategies/${strategy.id}/rules?term=${t}`}
          className="inline [&_a]:decoration-[1px] [&_a]:underline-offset-[3px]"
        />
      </div>
    ) : (
      <div className="min-w-0 truncate text-[13px] text-fg-2">{sub}</div>
    );

  return (
    <div className="page relative isolate">
      <Link
        to="/strategies"
        className="mb-2 inline-flex items-center gap-1 text-[13px] text-accent md:hidden"
      >
        <ChevronLeft className="h-4 w-4" />
        Strategies
      </Link>
      <header className="flex flex-col gap-2 border-b border-line md:flex-row md:items-end md:justify-between md:gap-6">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 md:pb-3">
          <h1 className="m-0 text-[24px] font-semibold leading-tight tracking-[-0.02em] text-fg md:text-[19px]">
            {strategy.name}
          </h1>
          {badges}
        </div>
        <nav
          role="tablist"
          aria-label="Strategy sections"
          className="no-scrollbar -mb-px flex gap-5 overflow-x-auto"
        >
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={t.key === tab}
              onClick={() =>
                navigate(
                  t.key === 'overview' ? `/strategies/${id}` : `/strategies/${id}/${t.key}`,
                  {
                    replace: true,
                  }
                )
              }
              className={`whitespace-nowrap border-b-2 pb-3 pt-1 text-[13.5px] transition-colors ${
                t.key === tab
                  ? 'border-fg font-semibold text-fg'
                  : 'border-transparent text-fg-2 hover:text-fg'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <div className="mb-5 mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        {subLine}
        <div className="flex flex-wrap items-center gap-2 md:flex-none">
          {!ss.loaded ? null : row ? (
            <>
              <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-secondary btn-sm">
                Backtest
              </Link>
              <Link to={`/trading/${row.session.id}`} className="btn btn-secondary btn-sm">
                Open session
              </Link>
              <Link
                to={`/strategies/${strategy.id}/edit`}
                className="btn btn-primary btn-sm max-md:hidden"
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </Link>
            </>
          ) : (
            <>
              <Link
                to={`/strategies/${strategy.id}/edit`}
                className="btn btn-secondary btn-sm max-md:hidden"
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </Link>
              <Link to={`/backtest?strategy=${strategy.id}`} className="btn btn-secondary btn-sm">
                Run a new backtest
              </Link>
              <button
                type="button"
                onClick={() => setDeploying(true)}
                className="btn btn-primary btn-sm"
              >
                <Play className="h-3.5 w-3.5" />
                Start in paper
              </button>
            </>
          )}
        </div>
      </div>
      {attention && <div className="mb-4">{attention}</div>}

      {!ss.loaded && tab !== 'rules' ? <SkeletonChart height={240} /> : null}
      {ss.loaded && tab === 'overview' && (
        <OverviewTab
          strategy={strategy}
          ss={ss}
          running={detail.session}
          latestRun={detail.run}
          sameRun={sameMeta ? sameRun : null}
          versions={versions.state.status === 'ready' ? versions.state.versions : []}
          model={model}
          onDeploy={() => setDeploying(true)}
        />
      )}
      {ss.loaded && tab === 'today' && (
        <HoldTodayTab strategy={strategy} ss={ss} running={detail.session} model={model} />
      )}
      {tab === 'rules' && <RulesTab strategy={strategy} model={model} />}
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
