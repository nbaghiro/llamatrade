import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { ChevronLeft } from 'lucide-react';
import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SleeveCardSkeleton } from '../../components/portfolio/PortfolioSkeleton';
import { ReconciliationPanel } from '../../components/portfolio/ReconciliationPanel';
import {
  rebalanceLabel,
  shortDate,
  sinceStart,
  sleeveRunState,
} from '../../components/portfolio/sleeveView';
import { WeightRows } from '../../components/portfolio/WeightRows';
import {
  AttentionLine,
  LoadingLabel,
  Money,
  Num,
  PanelError,
  Skeleton,
  StatusMark,
} from '../../components/ui';
import { causeSentence, dayChange } from '../../lib/portfolioView';

const MAX_LOTS = 8;

function Crumb() {
  return (
    <Link
      to="/portfolio"
      className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg max-md:text-[15px] max-md:text-accent"
    >
      <ChevronLeft className="h-4 w-4 md:hidden" />
      Portfolio <span className="max-md:hidden">/</span>
    </Link>
  );
}

export default function SleevePage() {
  const { sleeveId = '' } = useParams();
  const { sleeve, sleeveLoading, sleeveError, fetchSleeve } = usePortfolioStore();

  useEffect(() => {
    if (sleeveId) fetchSleeve(sleeveId);
  }, [sleeveId, fetchSleeve]);

  const current = sleeve?.sleeveId === sleeveId ? sleeve : null;

  if (!current) {
    return (
      <div className="page">
        <Crumb />
        {sleeveError ? (
          <div className="panel mt-4">
            <PanelError
              title="This sleeve couldn't be loaded"
              cause={causeSentence(sleeveError)}
              unaffected="The rest of your portfolio isn't affected."
              onRetry={() => fetchSleeve(sleeveId)}
              retrying={sleeveLoading}
            />
          </div>
        ) : (
          <div aria-busy="true" className="mt-2 grid gap-4">
            <LoadingLabel>Loading this sleeve</LoadingLabel>
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-16 w-full" />
            <SleeveCardSkeleton />
          </div>
        )}
      </div>
    );
  }

  const today = dayChange(current.value, current.dayReturnPct);
  const gained = sinceStart(current);
  const since = shortDate(current.startedAt);
  const meta = [
    `${current.holdings.length} ${current.holdings.length === 1 ? 'position' : 'positions'}`,
    current.rebalance.toLowerCase(),
    since ? `since ${since}` : '',
  ].filter(Boolean);
  const figures = [
    { label: 'Market value', node: <Num value={current.value} /> },
    { label: 'Today', node: <Money value={today} pnl /> },
    { label: since ? `Since ${since}` : 'Since start', node: <Money value={gained} pnl /> },
    {
      label: 'Sleeve cash',
      node:
        current.cash !== null ? <Num value={current.cash} /> : <span className="text-fg-3">—</span>,
    },
  ];
  const lots = [...current.lots]
    .sort((a, b) => (b.openedAt?.getTime() ?? 0) - (a.openedAt?.getTime() ?? 0))
    .slice(0, MAX_LOTS);

  return (
    <div className="page">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <Crumb />
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] max-md:mt-1.5 max-md:text-2xl">
            {current.name}
          </h1>
          <div className="mt-0.5 text-[13px] text-fg-3">{meta.join(' · ')}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusMark state={sleeveRunState(current)} />
          {current.strategyId && (
            <Link to={`/strategies/${current.strategyId}`} className="btn btn-secondary">
              Open strategy
            </Link>
          )}
          <Link to="/trading" className="btn btn-secondary">
            Sessions
          </Link>
        </div>
      </div>

      {current.frozen && (
        <AttentionLine
          className="mb-4"
          items={[
            {
              id: current.sleeveId,
              title: `${current.name} is frozen.`,
              detail:
                "The ledger's count for a holding here doesn't match what Alpaca reports. New orders for this sleeve wait until the difference is resolved, and nothing is adjusted automatically.",
            },
          ]}
        />
      )}

      <div className="panel mb-4 grid grid-cols-2 md:grid-cols-4">
        {figures.map((f, i) => (
          <div
            key={f.label}
            className={`px-[18px] py-3 ${i % 2 ? 'border-l border-line' : ''} ${
              i >= 2 ? 'max-md:border-t md:border-l' : ''
            }`}
          >
            <span className="kicker">{f.label}</span>
            <div className="mt-0.5 text-xl">{f.node}</div>
          </div>
        ))}
      </div>

      {current.frozen && (
        <div className="mb-4">
          <ReconciliationPanel sleeve={current} />
        </div>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="panel">
          <div className="flex items-center justify-between gap-2.5 border-b border-line px-4 py-3">
            <b className="font-semibold">Holdings</b>
            <span className="text-[12.5px] text-fg-3">{rebalanceLabel(current.rebalance)}</span>
          </div>
          <div className="px-4 py-3.5">
            {current.holdings.length > 0 ? (
              <WeightRows
                holdings={current.holdings}
                sleeveValue={current.value}
                targets={current.targets}
                frozen={current.frozen}
                full
              />
            ) : (
              <p className="m-0 text-[12.5px] text-fg-3">
                No open positions. This sleeve holds only cash right now.
              </p>
            )}
            {current.cash !== null && (
              <div className="mt-2 flex justify-between border-t border-line pt-2.5 text-[12.5px] text-fg-3">
                <span>Sleeve cash</span>
                <Num value={current.cash} />
              </div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="flex items-center justify-between gap-2.5 border-b border-line px-4 py-3">
            <b className="font-semibold">Open lots</b>
            <span className="text-[12.5px] text-fg-3">From the ledger</span>
          </div>
          {lots.length === 0 ? (
            <p className="m-0 px-4 py-3.5 text-[12.5px] text-fg-3">No open lots.</p>
          ) : (
            lots.map((lot, i) => (
              <div
                key={`${lot.symbol}-${i}`}
                className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 last:border-b-0"
              >
                <span>
                  <span className="num text-fg-3">{shortDate(lot.openedAt)}</span>{' '}
                  <span className="font-mono font-semibold">{lot.symbol}</span>{' '}
                  <Num value={lot.qty} dp={lot.qty % 1 ? 4 : 0} className="text-fg-2" />
                </span>
                <span className="text-[12.5px] text-fg-3">
                  at <Num value={lot.avgPrice} />
                </span>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}
