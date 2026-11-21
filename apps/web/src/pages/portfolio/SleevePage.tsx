import { usePortfolioStore, type SleeveDetail } from '@llamatrade/core/stores/portfolio';
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';

import { TopUpDialog } from '../../components/funding/TopUpDialog';
import { fillNote, useSaleHistory } from '../../components/portfolio/fillNotes';
import { etDayKey, type SleeveFill } from '../../components/portfolio/history';
import { ReconciliationPanel } from '../../components/portfolio/ReconciliationPanel';
import { SleeveCurve } from '../../components/portfolio/SleeveCurve';
import { shortDate, sinceStart, sleeveRunState } from '../../components/portfolio/sleeveView';
import { useAssetNames } from '../../components/portfolio/useAssetNames';
import { useEquityCurves } from '../../components/portfolio/useEquityCurves';
import {
  useAllActivity,
  useSessionForSleeve,
  useSleeveFills,
} from '../../components/portfolio/usePortfolioData';
import {
  AttentionLine,
  LoadingLabel,
  ModeBadge,
  Money,
  Num,
  PageHead,
  PanelError,
  Pct,
  Skeleton,
  SkeletonChart,
  SkeletonRows,
  StatusMark,
  WeightBar,
} from '../../components/ui';
import { formatMoney, formatNumber } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { causeSentence, dayChange, weightRows } from '../../lib/portfolioView';

const CRUMB = { label: 'Portfolio', to: '/portfolio' };
const MAX_FILLS = 6;

function Figure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <span className="kicker">{label}</span>
      <div className="mt-0.5 text-[17px] font-medium">{children}</div>
    </div>
  );
}

/** "Holds TLT and GLD at 60% and 40%, rebalanced monthly · Alpaca paper". */
function describe(s: SleeveDetail): string {
  const symbols = Object.keys(s.targets);
  const list = (items: string[]) =>
    items.length <= 2
      ? items.join(' and ')
      : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
  const holds =
    symbols.length > 4
      ? `Holds ${symbols.length} funds at fixed weights`
      : symbols.length
        ? `Holds ${list(symbols)} at ${list(symbols.map((k) => `${Math.round(s.targets[k] * 100)}%`))}`
        : s.holdings.length > 4
          ? `Holds ${s.holdings.length} positions`
          : s.holdings.length
            ? `Holds ${list(s.holdings.map((h) => h.symbol))}`
            : 'Holds cash';
  const rebalance = s.rebalance ? `, rebalanced ${s.rebalance.toLowerCase()}` : '';
  return `${holds}${rebalance} · Alpaca ${s.live ? 'live' : 'paper'}`;
}

const TH =
  'border-b border-line px-3 py-2.5 text-left font-mono text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3';
const TD = 'border-b border-line px-3 py-3';

function Holdings({
  sleeve,
  names,
}: {
  sleeve: SleeveDetail;
  names: Readonly<Record<string, string>>;
}) {
  const rows = weightRows(sleeve.holdings, sleeve.value, sleeve.targets);
  const cash = sleeve.cash;
  return (
    <section className="panel overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-[13px]">
        <thead>
          <tr>
            <th className={TH}>Holding</th>
            <th className={`${TH} text-right`}>Shares</th>
            <th className={`${TH} text-right`}>Avg cost</th>
            <th className={`${TH} text-right`}>Price</th>
            <th className={`${TH} text-right`}>Value</th>
            <th className={`${TH} text-right`}>Unrealized</th>
            <th className={TH}>Weight against target</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className={`${TD} text-fg-3`}>
                No open positions. This sleeve holds only cash right now.
              </td>
            </tr>
          )}
          {rows.map(({ holding: h, weight, target }) => (
            <tr key={h.symbol}>
              <td className={TD}>
                <Link
                  to={`/markets?symbol=${h.symbol}`}
                  className="font-mono font-semibold hover:underline"
                >
                  {h.symbol}
                </Link>
                {names[h.symbol] && (
                  <div className="max-w-[220px] truncate text-[12px] text-fg-3">
                    {names[h.symbol]}
                  </div>
                )}
              </td>
              <td className={`${TD} text-right`}>
                <Num value={h.qty} dp={h.qty % 1 ? 4 : 0} />
              </td>
              <td className={`${TD} text-right`}>
                <Num value={h.avgEntryPrice} />
              </td>
              <td className={`${TD} text-right`}>
                <Num value={h.price} />
              </td>
              <td className={`${TD} text-right`}>
                <Money value={h.marketValue} />
              </td>
              <td className={`${TD} text-right`}>
                <Money value={h.unrealizedPnl} pnl />
              </td>
              <td className={TD}>
                <div className="flex items-center gap-2.5">
                  <span className="num w-12 text-fg-2">{(weight * 100).toFixed(1)}%</span>
                  <WeightBar
                    weight={weight}
                    target={target}
                    frozen={sleeve.frozen}
                    height={6}
                    className="w-20"
                    label={`${h.symbol} weight`}
                  />
                  <span className="num text-fg-3">
                    {target !== undefined ? `${Math.round(target * 100)}%` : ''}
                  </span>
                </div>
              </td>
            </tr>
          ))}
          {cash !== null && (
            <tr>
              <td className={`${TD} font-mono font-semibold`}>Cash</td>
              <td className={`${TD} text-right text-fg-3`} colSpan={3}>
                ·
              </td>
              <td className={`${TD} text-right`}>
                <Money value={cash} />
              </td>
              <td className={`${TD} text-right text-fg-3`}>·</td>
              <td className={TD}>
                <span className="num text-fg-2">
                  {sleeve.value > 0 ? ((cash / sleeve.value) * 100).toFixed(1) : '0.0'}%
                </span>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function Fills({
  sleeve,
  fills,
  now,
}: {
  sleeve: SleeveDetail;
  fills: readonly SleeveFill[];
  now: Date;
}) {
  const todayKey = etDayKey(now);
  const todays = fills.filter((f) => etDayKey(f.at) === todayKey);
  const list = (todays.length ? todays : fills).slice(0, MAX_FILLS);
  const history = useSaleHistory(
    sleeve.accountId,
    list.filter((f) => f.side === 'sell').map((f) => f.symbol)
  );
  const noteText = (f: SleeveFill) => {
    const note = fillNote(f, sleeve.lots, history);
    if (note.kind === 'newLot') return 'new lot';
    if (note.kind === 'realized') return `realized ${formatMoney(note.amount, { signed: true })}`;
    return null;
  };
  return (
    <section className="panel">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <b className="font-semibold">{todays.length ? "Today's fills" : 'Latest fills'}</b>
        <span className="text-[12px] text-fg-3">From this sleeve&apos;s orders</span>
      </div>
      {list.length === 0 ? (
        <p className="m-0 px-4 py-3.5 text-[12.5px] text-fg-3">No fills yet.</p>
      ) : (
        list.map((f) => {
          const note = noteText(f);
          return (
            <div
              key={f.id}
              className="flex items-start gap-3 border-b border-line px-4 py-3 last:border-b-0"
            >
              <span className="mt-0.5 rounded-[3px] border border-line-strong px-1.5 font-mono text-[10.5px] uppercase text-fg-2">
                {f.side}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block">
                  {formatNumber(f.qty, { dp: f.qty % 1 ? 2 : 0 })} {f.symbol} at{' '}
                  {formatMoney(f.price)}
                </span>
                <span className="text-[12px] text-fg-3">
                  {todays.length ? etClock(f.at) : `${shortDate(f.at)} · ${etClock(f.at)}`}
                  {note ? ` · ${note}` : ''}
                </span>
              </span>
              <Money value={f.qty * f.price} className="text-[13px]" />
            </div>
          );
        })
      )}
      <p className="m-0 border-t border-line px-4 py-2.5 text-[12px] text-fg-3">
        {sleeve.frozen
          ? 'The ledger and Alpaca disagree on a holding here.'
          : 'No difference with Alpaca is open for this sleeve.'}
      </p>
    </section>
  );
}

export default function SleevePage() {
  const { sleeveId = '' } = useParams();
  const { sleeve, sleeveLoading, sleeveError, fetchSleeve } = usePortfolioStore();
  const [topUpOpen, setTopUpOpen] = useState(false);
  const [now] = useState(() => new Date());

  useEffect(() => {
    if (sleeveId) fetchSleeve(sleeveId);
  }, [sleeveId, fetchSleeve]);

  const current = sleeve?.sleeveId === sleeveId ? sleeve : null;
  const { fills: allFills } = useSleeveFills();
  const { rows } = useAllActivity();
  const sessionId = useSessionForSleeve(current?.sleeveId ?? null);
  const executionIds = current?.executionId ? [current.executionId] : [];
  const { curves } = useEquityCurves(executionIds, { benchmark: true });
  const names = useAssetNames(current?.holdings.map((h) => h.symbol) ?? []);

  if (!current) {
    return (
      <div className="page">
        <PageHead crumbs={[CRUMB]} title="Sleeve" />
        {sleeveError ? (
          <div className="panel">
            <PanelError
              title="This sleeve couldn't be loaded"
              cause={causeSentence(sleeveError)}
              unaffected="The rest of your portfolio isn't affected."
              onRetry={() => fetchSleeve(sleeveId)}
              retrying={sleeveLoading}
            />
          </div>
        ) : (
          <div aria-busy="true" className="grid gap-4">
            <LoadingLabel>Loading this sleeve</LoadingLabel>
            <Skeleton className="h-6 w-64" />
            <SkeletonChart height={300} />
            <SkeletonRows rows={3} cols={6} />
          </div>
        )}
      </div>
    );
  }

  const fills = allFills.filter((f) => f.sleeveId === current.sleeveId);
  const today = dayChange(current.value, current.dayReturnPct);
  const gained = sinceStart(current);
  const since = shortDate(current.startedAt);
  const state = sleeveRunState(current);

  return (
    <div className="page">
      <PageHead
        crumbs={[CRUMB, { label: current.name }]}
        title={current.name}
        badges={
          <>
            <ModeBadge mode={current.live ? 'live' : 'paper'} />
            <StatusMark state={state} />
          </>
        }
        sub={describe(current)}
        actions={
          <>
            {!current.live && state !== 'stopped' && !current.frozen && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setTopUpOpen(true)}
              >
                Top up
              </button>
            )}
            {sessionId ? (
              <Link to={`/trading/${sessionId}`} className="btn btn-primary">
                Open session
              </Link>
            ) : (
              current.strategyId && (
                <Link to={`/strategies/${current.strategyId}`} className="btn btn-primary">
                  Open strategy
                </Link>
              )
            )}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap gap-x-10 gap-y-3">
        <Figure label="Value">
          <Money value={current.value} />
        </Figure>
        <Figure label="Today">
          <Money value={today} pnl />
        </Figure>
        <Figure label={since ? `Since ${since}` : 'Since start'}>
          <Pct value={current.allocatedCapital > 0 ? gained / current.allocatedCapital : 0} pnl />
        </Figure>
        <Figure label={`Gain on ${formatMoney(current.allocatedCapital, { dp: 0 })} added`}>
          <Money value={gained} pnl />
        </Figure>
      </div>

      {current.frozen && (
        <>
          <AttentionLine
            className="mb-4"
            items={[
              {
                id: current.sleeveId,
                title: `${current.name} is frozen.`,
                detail:
                  "The ledger's count for a holding here doesn't match what Alpaca reports. New orders for this sleeve wait until the difference is resolved, and nothing is adjusted automatically.",
                action: (
                  <Link to="/portfolio/checks" className="btn btn-secondary btn-sm">
                    See the check
                  </Link>
                ),
              },
            ]}
          />
          <div className="mb-4">
            <ReconciliationPanel sleeve={current} />
          </div>
        </>
      )}

      <section className="panel-rim mb-4 px-5 pb-1.5 pt-4">
        <SleeveCurve
          sleeve={current}
          curve={curves[current.executionId] ?? null}
          fills={fills}
          rows={rows}
          now={now}
        />
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Holdings sleeve={current} names={names} />
        <Fills sleeve={current} fills={fills} now={now} />
      </div>

      {current.sleeveId && (
        <TopUpDialog
          open={topUpOpen}
          onClose={() => setTopUpOpen(false)}
          sleeve={{
            sleeveId: current.sleeveId,
            name: current.name,
            value: current.value,
            rebalance: current.rebalance,
          }}
          onDone={() => fetchSleeve(sleeveId)}
        />
      )}
    </div>
  );
}
