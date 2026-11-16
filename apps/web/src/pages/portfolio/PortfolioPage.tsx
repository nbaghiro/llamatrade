import { useFundingStore } from '@llamatrade/core/stores/funding';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { Layers, PlugZap } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AddFundsDialog } from '../../components/funding/AddFundsDialog';
import {
  AllocationBar,
  PortfolioHeader,
  PortfolioSkeleton,
  SleeveCard,
} from '../../components/portfolio';
import { shortDate, sinceStart } from '../../components/portfolio/sleeveView';
import {
  AttentionLine,
  EmptyState,
  Money,
  Num,
  PageArt,
  PanelError,
  Pct,
} from '../../components/ui';
import { formatMoney } from '../../lib/format';
import {
  accountTotals,
  causeSentence,
  dayChange,
  dayChangeFraction,
} from '../../lib/portfolioView';

/** Where "Deploy a strategy" opens the sessions package's deploy sheet. */
const DEPLOY_PATH = '/trading?deploy=1';

export default function PortfolioPage() {
  const navigate = useNavigate();
  const { sleeves, unallocated, summaryTotal, loading, loaded, error, fetchPortfolio } =
    usePortfolioStore();
  const { resolved, accountId } = useFundingStore();
  const [fundsOpen, setFundsOpen] = useState(false);
  const closeFunds = useCallback(() => setFundsOpen(false), []);
  const refresh = useCallback(() => fetchPortfolio(), [fetchPortfolio]);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  const [params, setParams] = useSearchParams();
  useEffect(() => {
    if (params.get('funds') !== 'add') return;
    setFundsOpen(true);
    setParams({}, { replace: true });
  }, [params, setParams]);

  const totals = useMemo(
    () =>
      accountTotals(
        sleeves.map((s) => s.value),
        unallocated,
        summaryTotal
      ),
    [sleeves, unallocated, summaryTotal]
  );
  const today = sleeves.reduce((sum, s) => sum + dayChange(s.value, s.dayReturnPct), 0);
  const gained = sleeves.reduce((sum, s) => sum + sinceStart(s), 0);
  const firstStart = sleeves
    .map((s) => s.startedAt)
    .filter((d): d is Date => d !== null)
    .sort((a, b) => a.getTime() - b.getTime())[0];
  const openPositions = sleeves.reduce((n, s) => n + s.holdings.length, 0);
  const frozen = sleeves.filter((s) => s.frozen);
  const firstLoad = !loaded || (loading && sleeves.length === 0 && !error);
  const noAccount = resolved && !accountId;

  return (
    <div className="page relative isolate">
      <PageArt shape="join" />
      <PortfolioHeader
        openPositions={firstLoad || (error && sleeves.length === 0) ? null : openPositions}
        loading={firstLoad}
        onAddFunds={() => setFundsOpen(true)}
        onDeploy={() => navigate(DEPLOY_PATH)}
      />

      {firstLoad ? (
        <PortfolioSkeleton />
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
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
            <div>
              <span className="kicker">Total equity</span>
              <Money
                value={totals.total}
                className="block text-[34px] font-medium leading-[1.1] tracking-[-0.03em] md:text-[36px]"
              />
            </div>
            <div className="num text-[14px] md:text-right">
              <span className={today > 0 ? 'text-gain' : today < 0 ? 'text-loss' : 'text-fg-2'}>
                <Money value={today} pnl /> today ·{' '}
                <Pct value={dayChangeFraction(totals.total, today)} pnl />
              </span>
              {firstStart && sleeves.length > 0 && (
                <div className="text-[12.5px] text-fg-3">
                  <Money value={gained} signed /> on sleeves since {shortDate(firstStart)}
                </div>
              )}
            </div>
          </div>

          <AllocationBar
            sleeves={sleeves.map((s) => ({
              id: s.executionId,
              label: s.name,
              value: s.value,
              frozen: s.frozen,
            }))}
            unallocated={totals.unallocated}
          />

          {unallocated === null && !noAccount && (
            <p className="mb-0 mt-2 text-[12.5px] text-fg-3">
              The ledger didn&apos;t answer, so unallocated cash is the account total less the
              sleeves.
            </p>
          )}

          {frozen.length > 0 && (
            <AttentionLine
              className="mt-4"
              items={frozen.map((s) => ({
                id: s.executionId,
                title: `${s.name} is frozen.`,
                detail:
                  'The ledger and Alpaca disagree on a holding in this sleeve. New orders for it wait until the difference is resolved.',
                action: s.sleeveId ? (
                  <Link
                    to={`/portfolio/sleeves/${s.sleeveId}`}
                    className="btn btn-secondary btn-sm"
                  >
                    Review
                  </Link>
                ) : undefined,
              }))}
            />
          )}

          {noAccount ? (
            <div className="panel mt-4">
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
          ) : sleeves.length === 0 ? (
            <div className="panel mt-4">
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
            <div className="mt-4 grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
              {sleeves.map((s, i) => (
                <SleeveCard key={s.executionId} sleeve={s} index={i} />
              ))}
            </div>
          )}

          <div className="rule-total mt-3.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-1 py-2.5">
            <span className="text-fg-2">
              Sleeves <Num value={totals.sleeves} /> + unallocated{' '}
              <Num value={totals.unallocated} />
            </span>
            <span className="num font-semibold">Total {formatMoney(totals.total)}</span>
          </div>
          {error && (
            <p role="alert" className="mt-2 text-[12.5px] text-risk">
              The last refresh failed. {causeSentence(error)} These figures are from the previous
              load.
            </p>
          )}
        </>
      )}

      <AddFundsDialog open={fundsOpen} onClose={closeFunds} totals={totals} onFunded={refresh} />
    </div>
  );
}
