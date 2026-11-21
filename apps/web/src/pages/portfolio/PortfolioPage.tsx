import { useFundingStore } from '@llamatrade/core/stores/funding';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { Layers, Plus, PlugZap, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AddFundsDialog } from '../../components/funding/AddFundsDialog';
import { AccountOverview } from '../../components/home/AccountOverview';
import { SleeveStatement } from '../../components/portfolio/SleeveStatement';
import { useEquityCurves } from '../../components/portfolio/useEquityCurves';
import { liveFreeCash, useLiveAccount } from '../../components/portfolio/useLiveAccount';
import { useResolvedSleeves } from '../../components/portfolio/usePortfolioData';
import { usePageScope } from '../../components/shell/usePageScope';
import {
  AttentionLine,
  EmptyState,
  LoadingLabel,
  PageHead,
  PanelError,
  ScopeControl,
  SkeletonRows,
} from '../../components/ui';
import { formatMoney } from '../../lib/format';
import { accountTotals, causeSentence } from '../../lib/portfolioView';
import { inScope } from '../../lib/scope';

/** Where "Start a strategy" opens the sessions package's deploy sheet. */
const DEPLOY_PATH = '/trading?deploy=1';

function SleevesSkeleton() {
  return (
    <div aria-busy="true" className="panel">
      <LoadingLabel>Loading your sleeves</LoadingLabel>
      <SkeletonRows rows={4} cols={6} />
    </div>
  );
}

export default function PortfolioPage() {
  const navigate = useNavigate();
  const {
    sleeves: portfolioSleeves,
    unallocated,
    summaryTotal,
    loading,
    loaded,
    error,
    fetchPortfolio,
  } = usePortfolioStore();
  const sleeves = useResolvedSleeves(portfolioSleeves);
  const { resolved, accountId } = useFundingStore();
  const [fundsOpen, setFundsOpen] = useState(false);
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
  const liveAccount = useLiveAccount();
  const liveFree = liveFreeCash(liveAccount);
  const liveTotal = liveSleeves.reduce((s, x) => s + x.value, 0) + (liveFree ?? 0);
  const allTotal = totals.total + liveTotal;

  const { scope, setScope, options } = usePageScope('portfolio', {
    all: allTotal,
    live: liveTotal,
    paper: totals.total,
  });

  const executionIds = useMemo(() => sleeves.map((s) => s.executionId), [sleeves]);
  const { curves } = useEquityCurves(executionIds);

  const indexed = sleeves.map((sleeve, index) => ({ sleeve, index }));
  const shown = indexed.filter(({ sleeve }) => inScope(scope, sleeve.live));
  const shownUnallocated = scope === 'live' ? null : totals.unallocated;
  const shownLiveFree = scope === 'paper' ? null : liveFree;
  const freeShown = (shownUnallocated ?? 0) + (shownLiveFree ?? 0);
  const shownSleeves = shown.map((x) => x.sleeve);
  const total = shownSleeves.reduce((s, x) => s + x.value, 0) + freeShown;
  const bothAccounts = options.filter((o) => o.key !== 'all').length > 1;

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
        Start a strategy
      </button>
    </>
  );

  return (
    <div className="page">
      <PageHead
        title="Portfolio"
        sub="Your account against SPY, each session's rules and holdings, and the cash in each sleeve."
        actions={actions}
        scope={
          options.length > 1 ? (
            <ScopeControl options={options} value={scope} onChange={setScope} />
          ) : undefined
        }
      />

      {!noAccount && (
        <div className="mb-6">
          <AccountOverview scope={scope} />
        </div>
      )}

      {firstLoad ? (
        <SleevesSkeleton />
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
            body="Your sleeves and paper funds live in an Alpaca paper account. Connect one to add funds and start strategies."
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

          <div className="mb-2 flex flex-wrap items-center gap-2.5">
            <h2 className="m-0 text-[15px] font-semibold">
              {scope === 'all' ? 'Sleeves' : scope === 'live' ? 'Live sleeves' : 'Paper sleeves'}
            </h2>
            {bothAccounts && scope !== 'all' && (
              <button
                type="button"
                className="inline-flex h-6 items-center gap-1.5 rounded-full border border-line-strong bg-sunk px-2.5 text-[12px] text-fg hover:border-accent"
                onClick={() => setScope('all')}
                aria-label={`Show both accounts, not ${scope} only`}
              >
                {scope === 'live' ? 'Live only' : 'Paper only'}
                <X className="h-3 w-3 text-fg-3" aria-hidden="true" />
              </button>
            )}
            {bothAccounts && scope !== 'all' && (
              <Link
                to="/portfolio/checks"
                className="ml-auto text-[12px] text-fg-3 hover:text-fg hover:underline max-md:hidden"
              >
                How this account compares with Alpaca
              </Link>
            )}
          </div>

          {sleeves.length === 0 ? (
            <div className="panel">
              <EmptyState
                icon={Layers}
                title="No strategies are running"
                body="Each strategy you start gets its own sleeve here. Until then, paper funds wait in unallocated cash."
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
                      Start a strategy
                    </button>
                  </>
                }
              />
            </div>
          ) : (
            <SleeveStatement
              sleeves={shown}
              unallocated={shownUnallocated}
              liveUnallocated={shownLiveFree}
              focus={bothAccounts && scope !== 'all' ? scope : null}
              curves={curves}
              now={now}
              footnote={
                bothAccounts && scope === 'all'
                  ? `Live ${formatMoney(liveTotal)} + paper ${formatMoney(totals.total)}`
                  : bothAccounts
                    ? `Sleeves ${formatMoney(total - freeShown)} + unallocated ${formatMoney(freeShown)}`
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
