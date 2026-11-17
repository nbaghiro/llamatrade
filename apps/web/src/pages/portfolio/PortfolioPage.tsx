import { useFundingStore } from '@llamatrade/core/stores/funding';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { Layers, Plus, PlugZap } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AddFundsDialog } from '../../components/funding/AddFundsDialog';
import { AccountSplit, type AccountHalf } from '../../components/portfolio/AccountSplit';
import { MoneyCurve, type MoneyRange } from '../../components/portfolio/MoneyCurve';
import { SleeveStatement } from '../../components/portfolio/SleeveStatement';
import { shortDate, sinceStart } from '../../components/portfolio/sleeveView';
import { useEquityCurves } from '../../components/portfolio/useEquityCurves';
import { useAllActivity, useSleeveFills } from '../../components/portfolio/usePortfolioData';
import { usePageScope } from '../../components/shell/usePageScope';
import {
  AttentionLine,
  EmptyState,
  LoadingLabel,
  Money,
  PageArt,
  PageHead,
  PanelError,
  Pct,
  Segmented,
  Skeleton,
  SkeletonChart,
  SkeletonRows,
} from '../../components/ui';
import { formatMoney } from '../../lib/format';
import {
  accountTotals,
  causeSentence,
  dayChange,
  dayChangeFraction,
} from '../../lib/portfolioView';
import { inScope } from '../../lib/scope';

/** Where "Deploy a strategy" opens the sessions package's deploy sheet. */
const DEPLOY_PATH = '/trading?deploy=1';

const RANGES: readonly { key: MoneyRange; label: string }[] = [
  { key: '1M', label: '1M' },
  { key: '3M', label: '3M' },
  { key: 'all', label: 'Since start' },
];

function Figure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <span className="kicker">{label}</span>
      <div className="mt-0.5 text-[17px] font-medium">{children}</div>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div aria-busy="true" className="grid gap-4">
      <LoadingLabel>Loading your portfolio</LoadingLabel>
      <div className="panel-rim grid gap-4 px-5 py-4">
        <Skeleton className="h-10 w-64" />
        <SkeletonChart height={260} />
      </div>
      <div className="panel">
        <SkeletonRows rows={4} cols={6} />
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  const navigate = useNavigate();
  const { sleeves, unallocated, summaryTotal, loading, loaded, error, fetchPortfolio } =
    usePortfolioStore();
  const { resolved, accountId } = useFundingStore();
  const [fundsOpen, setFundsOpen] = useState(false);
  const [range, setRange] = useState<MoneyRange>('all');
  const [now] = useState(() => new Date());
  const closeFunds = useCallback(() => setFundsOpen(false), []);
  const refresh = useCallback(() => fetchPortfolio(), [fetchPortfolio]);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  const [params, setParams] = useSearchParams();
  useEffect(() => {
    if (params.get('funds') !== 'add') return;
    setFundsOpen(true);
    const next = new URLSearchParams(params);
    next.delete('funds');
    setParams(next, { replace: true });
  }, [params, setParams]);

  const paperSleeves = sleeves.filter((s) => !s.live);
  const liveSleeves = sleeves.filter((s) => s.live);
  const totals = useMemo(
    () =>
      accountTotals(
        paperSleeves.map((s) => s.value),
        unallocated,
        summaryTotal
      ),
    [paperSleeves, unallocated, summaryTotal]
  );
  const liveTotal = liveSleeves.reduce((s, x) => s + x.value, 0);
  const allTotal = totals.total + liveTotal;

  const { scope, setScope, options } = usePageScope('portfolio', {
    all: allTotal,
    live: liveTotal,
    paper: totals.total,
  });

  const { rows } = useAllActivity();
  const { fills } = useSleeveFills();
  const executionIds = useMemo(() => sleeves.map((s) => s.executionId), [sleeves]);
  const { curves } = useEquityCurves(executionIds);

  const indexed = sleeves.map((sleeve, index) => ({ sleeve, index }));
  const shown = indexed.filter(({ sleeve }) => inScope(scope, sleeve.live));
  const shownUnallocated = scope === 'live' ? null : totals.unallocated;
  const shownSleeves = shown.map((x) => x.sleeve);
  const total = shownSleeves.reduce((s, x) => s + x.value, 0) + (shownUnallocated ?? 0);
  const today = shownSleeves.reduce((s, x) => s + dayChange(x.value, x.dayReturnPct), 0);
  const added = shownSleeves.reduce((s, x) => s + x.allocatedCapital, 0) + (shownUnallocated ?? 0);
  const gained = shownSleeves.reduce((s, x) => s + sinceStart(x), 0);
  const firstStart = shownSleeves
    .map((s) => s.startedAt)
    .filter((d): d is Date => d !== null)
    .sort((a, b) => a.getTime() - b.getTime())[0];

  const halfOf = (kind: 'live' | 'paper'): AccountHalf => {
    const list = kind === 'live' ? liveSleeves : paperSleeves;
    const label = options.find((o) => o.key === kind)?.label ?? kind;
    return {
      kind,
      label: `Alpaca ${label.replace(/^(Live|Paper)/, (m) => m.toLowerCase())}`,
      value: kind === 'live' ? liveTotal : totals.total,
      today: list.reduce((s, x) => s + dayChange(x.value, x.dayReturnPct), 0),
      sleeves: list.map((s) => ({ id: s.executionId, name: s.name, value: s.value })),
    };
  };
  const kinds = options.filter((o) => o.key !== 'all').map((o) => o.key as 'live' | 'paper');
  const halves = (kinds.length ? kinds : (['paper'] as const)).map(halfOf);
  const bothAccounts = halves.length > 1;
  const scopeName = scope === 'all' ? 'paper and live' : scope;

  const frozen = sleeves.filter((s) => s.frozen);
  const firstLoad = !loaded || (loading && sleeves.length === 0 && !error);
  const noAccount = resolved && !accountId;

  const actions = (
    <>
      <Link to="/portfolio/activity" className="btn btn-secondary">
        Activity
      </Link>
      <Link to="/portfolio/checks" className="btn btn-secondary max-md:hidden">
        Checks
      </Link>
      <button type="button" className="btn btn-secondary" onClick={() => setFundsOpen(true)}>
        <Plus className="h-3.5 w-3.5" />
        Add paper funds
      </button>
      <button type="button" className="btn btn-primary" onClick={() => navigate(DEPLOY_PATH)}>
        Deploy a strategy
      </button>
    </>
  );

  return (
    <div className="page relative isolate">
      <PageArt shape="join" />
      <PageHead
        title="Portfolio"
        sub="Where the money sits in each Alpaca account and how it got there."
        actions={actions}
      />

      {firstLoad ? (
        <OverviewSkeleton />
      ) : error && sleeves.length === 0 ? (
        <div className="panel">
          <PanelError
            title="Your portfolio couldn't be loaded"
            cause={causeSentence(error)}
            unaffected="Your sleeves and their orders aren't affected."
            onRetry={() => fetchPortfolio()}
            retrying={loading}
          />
        </div>
      ) : noAccount ? (
        <div className="panel">
          <EmptyState
            icon={PlugZap}
            title="Connect an Alpaca paper account"
            body="Your sleeves and paper funds live in an Alpaca paper account. Connect one to add funds and deploy strategies."
            actions={
              <Link to="/settings/broker" className="btn btn-primary">
                Connect paper account
              </Link>
            }
          />
        </div>
      ) : (
        <>
          {frozen.length > 0 && (
            <AttentionLine
              className="mb-4"
              items={frozen.map((s) => ({
                id: s.executionId,
                title: `${s.name} is frozen.`,
                detail:
                  'The ledger and Alpaca disagree on a holding in this sleeve. New orders for it wait until the difference is resolved.',
                action: (
                  <Link to="/portfolio/checks" className="btn btn-secondary btn-sm">
                    See the check
                  </Link>
                ),
              }))}
            />
          )}

          <section className="panel-rim mb-4 px-5 pb-1.5 pt-4">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
              <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
                <div>
                  <span className="kicker">Total equity · {scopeName}</span>
                  <div className="flex flex-wrap items-baseline gap-x-3">
                    <Money
                      value={total}
                      className="text-[34px] font-medium leading-[1.1] tracking-[-0.03em] md:text-[36px]"
                    />
                    <span className="text-[13px]">
                      <Money value={today} pnl /> ·{' '}
                      <Pct value={dayChangeFraction(total, today)} pnl />{' '}
                      <span className="text-fg-3">today</span>
                    </span>
                  </div>
                </div>
                {bothAccounts && scope === 'all' && (
                  <>
                    <Figure label="Live">
                      <Money value={liveTotal} />
                    </Figure>
                    <Figure label="Paper">
                      <Money value={totals.total} />
                    </Figure>
                  </>
                )}
                <Figure label="Money added">
                  <Money value={added} />
                </Figure>
                {firstStart && (
                  <Figure label={`Gain since ${shortDate(firstStart)}`}>
                    <Money value={gained} pnl />
                  </Figure>
                )}
              </div>
              <Segmented label="Range" options={RANGES} value={range} onChange={setRange} />
            </div>
            <MoneyCurve
              sleeves={shownSleeves}
              unallocated={shownUnallocated}
              rows={rows}
              fills={fills}
              curves={curves}
              range={range}
              now={now}
            />
          </section>

          <div className="mb-4">
            <AccountSplit halves={halves} scope={scope} onScope={setScope} />
          </div>

          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="m-0 text-[15px] font-semibold">
              {scope === 'all' ? 'Sleeves' : scope === 'live' ? 'Live sleeves' : 'Paper sleeves'}
            </h2>
            {bothAccounts && scope !== 'all' && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setScope('all')}
              >
                Show both accounts
              </button>
            )}
          </div>

          {sleeves.length === 0 ? (
            <div className="panel">
              <EmptyState
                icon={Layers}
                title="No strategies are deployed"
                body="Each deployed strategy gets its own sleeve here. Until then, paper funds wait in unallocated cash."
                actions={
                  <>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setFundsOpen(true)}
                    >
                      Add paper funds
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => navigate(DEPLOY_PATH)}
                    >
                      Deploy a strategy
                    </button>
                  </>
                }
              />
            </div>
          ) : (
            <SleeveStatement
              sleeves={shown}
              unallocated={shownUnallocated}
              footnote={
                bothAccounts && scope === 'all'
                  ? `Live ${formatMoney(liveTotal)} + paper ${formatMoney(totals.total)}`
                  : `${shown.length} ${shown.length === 1 ? 'sleeve' : 'sleeves'}${
                      shownUnallocated !== null ? ' + unallocated cash' : ''
                    }`
              }
            />
          )}

          {unallocated === null && (
            <p className="mb-0 mt-2 text-[12.5px] text-fg-3">
              The ledger didn&apos;t answer, so unallocated cash is the account total less the
              sleeves.
            </p>
          )}
          {error && (
            <p role="alert" className="mt-2 text-[12.5px] text-risk">
              The last refresh failed. {causeSentence(error)} These figures are from the previous
              load.
            </p>
          )}
        </>
      )}

      <AddFundsDialog
        open={fundsOpen}
        onClose={closeFunds}
        totals={totals}
        sleeves={paperSleeves}
        onFunded={refresh}
      />
    </div>
  );
}
