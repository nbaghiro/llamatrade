import type { SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { useMemo, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatNumber } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { nextRebalanceDate } from '../../lib/sessionState';
import { sleeveColor, sleeveRunState } from '../portfolio/sleeveView';
import { dayLabel } from '../sessions/sessionRows';
import { EmptyState, PanelError, Segmented, Skeleton } from '../ui';

import { HoldingsMap } from './HoldingsMap';
import {
  cashLine,
  dayMoves,
  mapTiles,
  moveClass,
  pctText,
  shares,
  type CashLine,
  type DayMoves,
  type Holder,
  type MapTile,
} from './marketsView';
import { SymbolChart } from './SymbolChart';
import { TINT_CAP_PCT } from './treemap';
import { RANGES, type MarketsModel } from './useMarketsModel';

const signedMoney = (v: number) => formatMoney(v, { signed: true });

function Swatch({ index }: { index: number }) {
  return (
    <i
      aria-hidden="true"
      className="inline-block h-2 w-2 flex-none rounded-[2px]"
      style={{ background: sleeveColor(index) }}
    />
  );
}

function CashNote({ cash, compact }: { cash: CashLine<SleeveSummary>; compact: boolean }) {
  const amount = formatMoney(cash.total);
  if (compact) return <p className="m-0 text-[11.5px] text-fg-3">{amount} in cash is not shown.</p>;
  const most = cash.most;
  let where = '';
  if (most && most.sleeve === null) where = ' Most of it is not in any sleeve.';
  else if (most?.sleeve) {
    const state = sleeveRunState(most.sleeve);
    const note =
      state === 'running' ? '' : `, which is ${state === 'waiting' ? 'waiting for data' : state}`;
    where = ` Most of it is in ${most.sleeve.name}${note}.`;
  }
  return (
    <div className="mt-2 flex items-center gap-3 rounded-[8px] border border-dashed border-line-strong px-3 py-2 text-[12.5px] text-fg-2">
      <i
        aria-hidden="true"
        className="h-2 w-2 flex-none rounded-[2px] border border-line-strong bg-sunk"
      />
      <span>
        <b className="num font-semibold text-fg">{amount}</b> in cash is not on the map.{where}
      </span>
    </div>
  );
}

function TodayPanel({ moves, now }: { moves: DayMoves; now: Date }) {
  return (
    <section className="panel rounded-[10px] px-4 py-3.5">
      <h2 className="kicker m-0">On your shares today</h2>
      <div
        className={`num mt-1.5 text-[30px] font-medium tracking-[-0.03em] ${moveClass(moves.total)}`}
      >
        {signedMoney(moves.total)}
      </div>
      <div className="mt-0.5 text-[11.5px] text-fg-3">
        {formatMoney(moves.held)} held · {etClock(now)} ET · IEX
      </div>
      {moves.movers.length > 0 && (
        <dl className="m-0 mt-2.5">
          {moves.movers.map((m) => (
            <div
              key={m.symbol}
              className="flex justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0"
            >
              <dt className="text-fg-2">{m.symbol}</dt>
              <dd className={`num m-0 ${moveClass(m.move)}`}>{signedMoney(m.move)}</dd>
            </div>
          ))}
        </dl>
      )}
      {moves.missing.length > 0 && (
        <p className="m-0 mt-2 text-[11.5px] text-fg-3">
          No price yet for {moves.missing.join(', ')}, so{' '}
          {moves.missing.length === 1 ? 'it is' : 'they are'} not counted.
        </p>
      )}
      <p className="m-0 mt-2 text-[11.5px] text-fg-3">
        Today&apos;s price change times the shares held now.
      </p>
    </section>
  );
}

function TintScale() {
  const steps: { tone: 'gain' | 'loss' | 'flat'; s: number }[] = [
    { tone: 'loss', s: 1 },
    { tone: 'loss', s: 0.25 },
    { tone: 'flat', s: 0 },
    { tone: 'gain', s: 0.25 },
    { tone: 'gain', s: 1 },
  ];
  return (
    <div
      className="flex items-center gap-1.5 font-mono text-[10.5px] text-fg-3"
      aria-label={`Tile colour runs from a ${TINT_CAP_PCT}% fall to a ${TINT_CAP_PCT}% rise or more`}
      role="img"
    >
      <span>−{TINT_CAP_PCT}%</span>
      {steps.map((st, i) => (
        <i
          key={i}
          data-tone={st.tone}
          className={`tile-tint h-2.5 w-[18px] rounded-[2px] ${st.tone === 'flat' ? 'border border-line' : ''}`}
          style={{ '--tile-s': st.s } as CSSProperties}
        />
      ))}
      <span>+{TINT_CAP_PCT}%</span>
    </div>
  );
}

function SleeveCard({ h, today }: { h: Holder; today: Date }) {
  const next = h.running ? nextRebalanceDate(h.rebalance, today) : null;
  const weight = `${(h.weight * 100).toFixed(1)}%${
    h.target !== undefined ? ` of ${Math.round(h.target * 100)}%` : ' of sleeve'
  }`;
  const when = next
    ? `Rebalances ${dayLabel(next)}`
    : h.running
      ? 'No set rebalance date'
      : 'Not running';
  return (
    <section
      className={`rounded-[10px] bg-panel px-3 py-2.5 ${
        h.live ? 'border-[1.5px] border-fg' : 'border border-dashed border-line-strong'
      }`}
    >
      <div className="flex items-center gap-2 text-[13px]">
        <Swatch index={h.index} />
        {h.sleeveId ? (
          <Link
            to={`/portfolio/sleeves/${h.sleeveId}`}
            className="truncate font-semibold hover:underline"
          >
            {h.name}
          </Link>
        ) : (
          <b className="truncate font-semibold">{h.name}</b>
        )}
        <span className="sr-only">{h.live ? ', live' : ', paper'}</span>
        <span className="flex-1" />
        <span className="num whitespace-nowrap">
          {shares(h.qty)} ·{' '}
          <span className={moveClass(h.unrealized)}>{signedMoney(h.unrealized)}</span>
        </span>
      </div>
      <div className="mt-1 text-[11.5px] text-fg-3">
        Avg <span className="num">{h.avgCost.toFixed(2)}</span> · {weight} · {when}
      </div>
    </section>
  );
}

function ChartHead({ m, compact }: { m: MarketsModel; compact: boolean }) {
  const q = m.quote;
  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
      <h2 className={`m-0 font-mono font-semibold ${compact ? 'text-[16px]' : 'text-[17px]'}`}>
        {m.symbol}
      </h2>
      {!compact && m.series.name && (
        <span className="hidden truncate text-[12.5px] text-fg-3 xl:inline">{m.series.name}</span>
      )}
      <span className="flex-1" />
      {q && <span className="num text-[14px]">{q.price.toFixed(2)}</span>}
      {q && (
        <span
          className={`num rounded-[4px] bg-sunk px-1.5 py-0.5 text-[12.5px] ${moveClass(q.changePercent)}`}
        >
          {!compact && `${formatNumber(q.change, { signed: true })} · `}
          {pctText(q.changePercent)}
        </span>
      )}
      {!compact && (
        <Segmented label="Range" options={RANGES} value={m.range} onChange={m.setRange} />
      )}
    </div>
  );
}

/** One short line naming who holds the symbol, for the phone card. */
function holdersLine(holders: readonly Holder[], tile: MapTile | undefined): string {
  const parts = holders.map((h) => `${h.initials} ${shares(h.qty)} ${h.live ? 'live' : 'paper'}`);
  if (tile?.dayMove !== null && tile?.dayMove !== undefined)
    parts.push(`${signedMoney(tile.dayMove)} today`);
  return parts.length ? parts.join(' · ') : 'Not held in any sleeve';
}

/** The map view: holdings as tiles, today's move on them, and the picked symbol's chart (markets E). */
export function MarketsMapView({ m, compact }: { m: MarketsModel; compact: boolean }) {
  const tiles = useMemo(() => mapTiles(m.held, m.quotes, m.equity), [m.held, m.quotes, m.equity]);
  const moves = useMemo(() => dayMoves(tiles), [tiles]);
  const cash = useMemo(() => cashLine(m.sleeves, m.unallocated), [m.sleeves, m.unallocated]);
  const tile = tiles.find((t) => t.symbol === m.symbol);
  const holdingSleeves = useMemo(() => {
    const seen = new Map<number, string>();
    for (const r of m.held) for (const h of r.holders) seen.set(h.index, h.name);
    return [...seen.entries()].sort((a, b) => a[0] - b[0]);
  }, [m.held]);
  const mapHeight = compact ? 250 : 340;

  const map = !m.loaded ? (
    m.portfolioError ? (
      <div className="panel">
        <PanelError
          title="Your holdings couldn't be loaded"
          cause={m.portfolioError}
          onRetry={m.retryPortfolio}
        />
      </div>
    ) : (
      <Skeleton className="w-full rounded-[10px]" style={{ height: mapHeight }} />
    )
  ) : tiles.length === 0 ? (
    <EmptyState
      title="Your sleeves don't hold any shares yet"
      body="When a sleeve buys, each symbol shows here, sized by the dollars in it."
    />
  ) : (
    <HoldingsMap
      tiles={tiles}
      selected={m.symbol}
      onSelect={m.select}
      height={mapHeight}
      compact={compact}
      sparks={m.sparks}
    />
  );

  const chart = (
    <SymbolChart
      symbol={m.symbol}
      label={`${m.symbol} prices, ${m.rangeLabel}`}
      series={m.series}
      intraday={m.intraday}
      holders={m.holders}
      fills={m.fillMarks}
      height={compact ? 120 : 220}
      onRetry={m.retrySeries}
      costLabels={!compact}
    />
  );

  if (compact) {
    return (
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3">
        {map}
        {cash && cash.total > 0 && <CashNote cash={cash} compact />}
        <section className="rounded-[12px] border border-line bg-panel px-3.5 py-3">
          <ChartHead m={m} compact />
          <div className="mt-2">{chart}</div>
          <p className="m-0 mt-2 text-[11.5px] text-fg-3">{holdersLine(m.holders, tile)}</p>
        </section>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
      <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          {map}
          {cash && cash.total > 0 && <CashNote cash={cash} compact={false} />}
        </div>
        <div className="flex min-w-0 flex-col gap-3.5">
          {m.loaded && tiles.length > 0 && <TodayPanel moves={moves} now={m.now} />}
          {tiles.length > 0 && <TintScale />}
          {holdingSleeves.length > 0 && (
            <ul className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1.5 p-0 text-[11.5px] text-fg-2">
              {holdingSleeves.map(([index, name]) => (
                <li key={index} className="flex items-center gap-1.5">
                  <Swatch index={index} />
                  {name}
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-fg-2">
            <span className="mr-0.5">Watching</span>
            {m.watchOnly.length === 0 && (
              <span className="text-fg-3">Add symbols to watch from the List view.</span>
            )}
            {m.watchOnly.map((s) => {
              const q = m.quotes[s];
              const on = s === m.symbol;
              return (
                <button
                  key={s}
                  type="button"
                  aria-pressed={on}
                  onClick={() => m.select(s)}
                  title={q ? `${s} ${pctText(q.changePercent)} today` : s}
                  className={`h-7 rounded-full border px-3 font-mono text-[12px] font-medium text-fg ${
                    on
                      ? 'border-accent bg-[var(--accent-soft)]'
                      : 'border-line-strong bg-panel hover:border-fg-3'
                  }`}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="panel min-w-0 rounded-[10px] px-4 py-3.5">
          <ChartHead m={m} compact={false} />
          <div className="mt-2.5">{chart}</div>
          <div className="mt-2 flex flex-wrap justify-between gap-x-4 gap-y-1 text-[11.5px] text-fg-3">
            <span>
              B buy · S sell, paper in colour, live in ink
              {m.holders.length > 0 && ". Lines are each sleeve's average cost"}
            </span>
            <span>{m.intraday ? 'Intraday' : 'Daily'} bars from Alpaca&apos;s IEX feed</span>
          </div>
        </section>
        <div className="flex min-w-0 flex-col gap-2.5">
          {m.holders.length > 0 ? (
            m.holders.map((h) => <SleeveCard key={h.executionId} h={h} today={m.today} />)
          ) : (
            <p className="m-0 text-[12.5px] text-fg-3">
              {m.symbol} is not held in any sleeve. A sleeve buys it only when its strategy includes
              it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
