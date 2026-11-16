import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { Plus } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import ActiveStrategies from '../../components/dashboard/ActiveStrategies';
import RecentActivity from '../../components/dashboard/RecentActivity';
import { sessionsSummary } from '../../components/home/attention';
import { EquityPanel, EquityPanelEmpty } from '../../components/home/EquityPanel';
import { HomeAttention } from '../../components/home/HomeAttention';
import { SetupSteps } from '../../components/home/SetupSteps';
import { StarterTemplates } from '../../components/home/StarterTemplates';
import { useAttentionEntries } from '../../components/home/useAttentionEntries';
import {
  LoadingLabel,
  PageArt,
  PanelError,
  SkeletonChart,
  SkeletonFigure,
  SkeletonRows,
} from '../../components/ui';
import { useAuthStore } from '../../store/auth';
import { deriveSetupSteps, useOnboardingStore, userOnboarding } from '../../store/onboarding';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

function greetingWord(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

const longDate = (d: Date) =>
  d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-panel border border-line bg-panel">{children}</div>
  );
}

function LoadingHome() {
  return (
    <>
      <LoadingLabel>Loading Home</LoadingLabel>
      <div className="grid grid-cols-[minmax(0,1fr)] overflow-hidden rounded-panel border border-line bg-panel md:grid-cols-[280px_minmax(0,1fr)]">
        <div className="border-b border-line p-4 md:border-b-0 md:border-r">
          <SkeletonFigure />
          <div className="mt-5">
            <SkeletonRows rows={4} cols={2} />
          </div>
        </div>
        <div className="p-4">
          <SkeletonChart height={250} />
        </div>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Panel>
          <SkeletonRows rows={3} cols={4} />
        </Panel>
        <Panel>
          <SkeletonRows rows={4} cols={2} />
        </Panel>
      </div>
    </>
  );
}

/** Home, account first: the attention line, the equity panel, then strategies and activity. */
export default function DashboardPage() {
  const fetchDashboard = useDashboardStore((s) => s.fetchDashboard);
  const loaded = useDashboardStore((s) => s.loaded);
  const loading = useDashboardStore((s) => s.loading);
  const error = useDashboardStore((s) => s.error);
  const strategies = useDashboardStore((s) => s.strategies);
  const liveCount = useDashboardStore((s) => s.liveStrategiesCount);
  const strategyCount = useDashboardStore((s) => s.strategyCount);
  const completedBacktestCount = useDashboardStore((s) => s.completedBacktestCount);
  const brokerConnected = useDashboardStore((s) => s.brokerConnected);
  const sessionCount = useDashboardStore((s) => s.sessionCount);
  const user = useAuthStore((s) => s.user);
  const byUser = useOnboardingStore((s) => s.byUser);
  const dismissSetup = useOnboardingStore((s) => s.dismissSetup);
  const attention = useAttentionEntries();
  const navigate = useNavigate();
  const createNew = useStrategyBuilderStore((s) => s.createNew);
  const newStrategy = () => {
    createNew();
    navigate('/strategies/builder');
  };

  useEffect(() => {
    fetchDashboard().catch(() => undefined);
  }, [fetchDashboard]);

  const progress = useMemo(
    () =>
      deriveSetupSteps({
        strategyCount,
        completedBacktestCount,
        brokerConnected,
        sessionCount: sessionCount ?? (loaded && !error ? strategies.length : null),
      }),
    [
      strategyCount,
      completedBacktestCount,
      brokerConnected,
      sessionCount,
      loaded,
      error,
      strategies.length,
    ]
  );
  const dismissed = userOnboarding(byUser, user?.id).setupDismissed;
  const noSessions = (sessionCount ?? strategies.length) === 0;
  const firstVisit = loaded && !error && noSessions && !progress.complete;

  const now = new Date();
  const name = user?.firstName?.trim();
  const greeting = firstVisit
    ? `Welcome${name ? `, ${name}` : ''}.`
    : `${greetingWord(now.getHours())}${name ? `, ${name}` : ''}.`;
  const meta =
    !loaded || error
      ? longDate(now)
      : firstVisit
        ? `${longDate(now)} · ${
            brokerConnected === false
              ? "Alpaca paper isn't connected yet"
              : `${progress.doneCount} of ${progress.steps.length} setup steps done`
          }`
        : `${longDate(now)} · ${sessionsSummary(liveCount, attention.length)}`;

  let body;
  if (!loaded) {
    body = <LoadingHome />;
  } else if (error) {
    body = (
      <Panel>
        <PanelError
          title="Home couldn't be loaded"
          cause="The portfolio service didn't answer."
          unaffected="Running paper sessions aren't affected."
          onRetry={() => fetchDashboard().catch(() => undefined)}
          retrying={loading}
        />
      </Panel>
    );
  } else if (firstVisit) {
    body = (
      <>
        {!dismissed && (
          <SetupSteps progress={progress} onHide={() => dismissSetup(user?.id ?? '')} />
        )}
        <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <StarterTemplates />
          <EquityPanelEmpty />
        </div>
      </>
    );
  } else {
    body = (
      <>
        <EquityPanel />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <ActiveStrategies />
          <RecentActivity />
        </div>
      </>
    );
  }

  return (
    <div className="page relative isolate grid grid-cols-[minmax(0,1fr)] gap-3">
      <PageArt shape="top" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="m-0 text-[27px] font-semibold leading-tight tracking-[-0.02em] md:text-[21px] md:tracking-[-0.015em]">
            {greeting}
          </h1>
          <div className="mt-[3px] text-[12.5px] text-fg-3">{meta}</div>
        </div>
        <div className="hidden items-center gap-2 md:flex">
          {firstVisit ? (
            <Link to="/strategies/templates" className="btn btn-secondary">
              Templates
            </Link>
          ) : (
            <Link to="/backtest" className="btn btn-secondary">
              Run backtest
            </Link>
          )}
          <button type="button" onClick={newStrategy} className="btn btn-primary">
            <Plus aria-hidden="true" className="h-4 w-4" />
            New strategy
          </button>
        </div>
      </header>
      {loaded && !error && <HomeAttention entries={attention} />}
      {body}
    </div>
  );
}
