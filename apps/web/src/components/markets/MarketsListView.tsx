import { Search, X } from 'lucide-react';
import { useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatNumber, moveTone, TONE_TEXT } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { nextRebalanceDate } from '../../lib/sessionState';
import { Sparkline } from '../charts';
import { shortDate, sleeveColor } from '../portfolio/sleeveView';
import { dayLabel } from '../sessions/sessionRows';
import { ModeBadge, Money, Num, Pct, Segmented } from '../ui';

import { cleanSymbol, shares, type Holder } from './marketsView';
import { SymbolChart } from './SymbolChart';
import { RANGES, type MarketsModel } from './useMarketsModel';

function ChangeText({ value, pct }: { value: number; pct: number }) {
  return (
    <span className={`num ${moveTone(pct) === 'flat' ? 'text-fg-3' : TONE_TEXT[moveTone(pct)]}`}>
      {formatNumber(pct, { signed: true })}%
      <span className="sr-only"> ({formatMoney(value, { signed: true })})</span>
    </span>
  );
}

function WatchItem({
  symbol,
  sub,
  price,
  pct,
  change,
  spark,
  active,
  onSelect,
  onRemove,
}: {
  symbol: string;
  sub: ReactNode;
  price: number | null;
  pct: number;
  change: number;
  spark: readonly number[];
  active: boolean;
  onSelect: () => void;
  onRemove?: () => void;
}) {
  return (
    <div
      className={`group relative flex items-center gap-3 rounded-[8px] border-l-2 px-3 py-2 ${
        active ? 'border-accent bg-sunk' : 'border-transparent hover:bg-sunk/60'
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        className="absolute inset-0 rounded-[8px]"
        aria-label={`Show ${symbol}`}
      />
      <span className="w-12 flex-none font-mono text-[13px] font-semibold">{symbol}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[11.5px] text-fg-3">{sub}</span>
        {spark.length > 1 && (
          <Sparkline
            values={spark}
            width={110}
            height={18}
            tone="neutral"
            label={`${symbol} last month`}
          />
        )}
      </span>
      <span className="text-right">
        <span className="num block text-[13px]">{price !== null ? price.toFixed(2) : '·'}</span>
        <span className="text-[11.5px]">
          <ChangeText value={change} pct={pct} />
        </span>
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Stop watching ${symbol}`}
          className="relative z-10 hidden h-5 w-5 place-items-center rounded text-fg-3 hover:text-fg group-hover:grid"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function HolderCard({ h, today }: { h: Holder; today: Date }) {
  const next = h.running ? nextRebalanceDate(h.rebalance, today) : null;
  const rows: [string, ReactNode][] = [
    [
      'Shares',
      <>
        {shares(h.qty)} · <Money value={h.marketValue} />
      </>,
    ],
    [
      'Avg cost',
      <>
        <Num value={h.avgCost} /> · <Money value={h.unrealized} pnl />
      </>,
    ],
    [
      'Weight',
      <>
        {(h.weight * 100).toFixed(1)}%
        {h.target !== undefined && ` of ${Math.round(h.target * 100)}%`}
      </>,
    ],
    ['Next rebalance', next ? dayLabel(next) : h.running ? 'No fixed date' : 'Not running'],
  ];
  return (
    <section
      className={`rounded-[10px] bg-panel px-4 py-3 ${
        h.live ? 'border border-fg' : 'border border-dashed border-fg-3'
      }`}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          <i
            aria-hidden="true"
            className="h-2 w-2 flex-none rounded-[2px]"
            style={{ background: sleeveColor(h.index) }}
          />
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
        </span>
        <ModeBadge mode={h.live ? 'live' : 'paper'} size="sm" />
      </div>
      <dl className="m-0">
        {rows.map(([k, v]) => (
          <div
            key={k}
            className="flex items-baseline justify-between gap-3 border-b border-line py-2 text-[12.5px] last:border-b-0"
          >
            <dt className="text-fg-2">{k}</dt>
            <dd className="num m-0 text-right">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The three-column view: watchlist, a large chart and who holds the symbol (markets2 A). */
export function MarketsListView({ m }: { m: MarketsModel }) {
  const [query, setQuery] = useState('');
  const { symbol, quote, series, stats, holders, quotes, sparks, held, watchOnly, watching } = m;
  const { select, watch, sleeveById, symbolFills, intraday } = m;
  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const s = cleanSymbol(query);
    if (!s) return;
    if (!m.heldSymbols.includes(s) && !watching.includes(s)) m.watch([...watching, s]);
    m.select(s);
    setQuery('');
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)_300px]">
      <aside className="order-3 lg:order-1 lg:row-span-2 xl:row-span-1">
        <form onSubmit={onSearch} className="relative mb-4">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-3"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search symbols"
            aria-label="Add or open a symbol"
            className="h-10 w-full rounded-full border border-line bg-sunk pl-9 pr-3 text-[13.5px] outline-none focus:border-accent"
          />
        </form>
        <div className="kicker mb-1 flex justify-between px-3">
          <span>In your sleeves</span>
          <span className="num">{held.length}</span>
        </div>
        {held.length === 0 && (
          <p className="m-0 px-3 py-2 text-[12.5px] text-fg-3">
            {m.loaded ? 'No sleeve holds anything yet.' : 'Loading your holdings.'}
          </p>
        )}
        {held.map((r) => {
          const q = quotes[r.symbol];
          return (
            <WatchItem
              key={r.symbol}
              symbol={r.symbol}
              sub={
                <span className="inline-flex items-center gap-1">
                  {r.holders.map((h) => (
                    <i
                      key={h.executionId}
                      aria-hidden="true"
                      className="h-1.5 w-1.5 rounded-[1px]"
                      style={{ background: sleeveColor(h.index) }}
                    />
                  ))}
                  {r.holders.map((h) => `${h.initials} ${shares(h.qty)}`).join(' · ')}
                </span>
              }
              price={q?.price ?? null}
              pct={q?.changePercent ?? 0}
              change={q?.change ?? 0}
              spark={sparks[r.symbol] ?? []}
              active={r.symbol === symbol}
              onSelect={() => select(r.symbol)}
            />
          );
        })}
        <div className="kicker mb-1 mt-4 px-3">Watching</div>
        {watchOnly.length === 0 && (
          <p className="m-0 px-3 py-2 text-[12.5px] text-fg-3">
            Search for a symbol to watch it here.
          </p>
        )}
        {watchOnly.map((s) => {
          const q = quotes[s];
          return (
            <WatchItem
              key={s}
              symbol={s}
              sub="Not held"
              price={q?.price ?? null}
              pct={q?.changePercent ?? 0}
              change={q?.change ?? 0}
              spark={sparks[s] ?? []}
              active={s === symbol}
              onSelect={() => select(s)}
              onRemove={() => watch(watching.filter((w) => w !== s))}
            />
          );
        })}
        <p className="m-0 mt-2 px-3 text-[11.5px] text-fg-3">
          The watched list is kept in this browser.
        </p>
      </aside>

      <main className="order-1 min-w-0 lg:order-2">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="m-0 font-mono text-[26px] font-semibold tracking-[-0.02em]">{symbol}</h2>
          <span className="truncate text-[13px] text-fg-2">
            {[series.name, series.exchange].filter(Boolean).join(' · ')}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <span className="num text-[34px] font-medium tracking-[-0.03em]">
              {quote ? quote.price.toFixed(2) : '·'}
            </span>
            {quote && (
              <span className="num text-[13px]">
                <span className={TONE_TEXT[moveTone(quote.changePercent)]}>
                  {formatNumber(quote.change, { signed: true })} ·{' '}
                  {formatNumber(quote.changePercent, { signed: true })}%
                </span>
              </span>
            )}
            <span className="text-[12px] text-fg-3">{etClock(m.now)} ET · IEX</span>
          </div>
          <Segmented label="Range" options={RANGES} value={m.range} onChange={m.setRange} />
        </div>

        <div className="mt-4">
          <SymbolChart
            symbol={symbol}
            label={`${symbol} prices, ${m.rangeLabel}`}
            series={series}
            intraday={intraday}
            holders={holders}
            fills={m.fillMarks}
            height={340}
            onRetry={m.retrySeries}
          />
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-fg-3">
          <span className="flex flex-wrap gap-x-4">
            <span>B buy · S sell, paper in colour, live in ink</span>
            {holders.length > 0 && <span>Lines are each sleeve&apos;s average cost</span>}
          </span>
          <span>
            {intraday ? 'Intraday' : 'Daily'} bars from Alpaca&apos;s IEX feed, which covers part of
            market volume
          </span>
        </div>

        {stats && (
          <dl className="panel m-0 mt-4 grid grid-cols-2 md:grid-cols-5">
            {[
              ['Open', <Num key="o" value={stats.open} />],
              [
                'Day range',
                <span key="r" className="num">
                  {stats.dayLow.toFixed(2)} to {stats.dayHigh.toFixed(2)}
                </span>,
              ],
              [m.sinceLabel, <Pct key="c" value={stats.change} pnl />],
              ['High in range', <Num key="h" value={stats.high} />],
              ['Volume, IEX', <Num key="v" value={stats.volume} dp={0} />],
            ].map(([k, v], i) => (
              <div
                key={String(k)}
                className={`px-4 py-3 ${i > 0 ? 'md:border-l md:border-line' : ''} ${i >= 2 ? 'max-md:border-t max-md:border-line' : ''}`}
              >
                <dt className="kicker">{k}</dt>
                <dd className="m-0 mt-1 text-[16px]">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </main>

      <aside className="order-2 min-w-0 lg:order-3 lg:col-start-2 xl:col-start-3">
        <h2 className="m-0 text-[17px] font-semibold">
          {holders.length
            ? `Held in ${holders.length} ${holders.length === 1 ? 'sleeve' : 'sleeves'}`
            : 'Not held in any sleeve'}
        </h2>
        {holders.length > 0 ? (
          <p className="m-0 mt-0.5 text-[12.5px] text-fg-3">
            {shares(m.heldQty)} shares · {formatMoney(m.heldValue)}
            {m.equity > 0 && ` · ${((m.heldValue / m.equity) * 100).toFixed(1)}% of your equity`}
          </p>
        ) : (
          <p className="m-0 mt-0.5 text-[12.5px] text-fg-3">
            A sleeve buys {symbol} only when its strategy includes it.
          </p>
        )}
        <div className="mt-3 grid gap-3">
          {holders.map((h) => (
            <HolderCard key={h.executionId} h={h} today={m.today} />
          ))}
        </div>
        {symbolFills.length > 0 && (
          <>
            <div className="kicker mb-1 mt-5">Fills</div>
            {symbolFills.slice(0, 8).map((f) => {
              const s = sleeveById.get(f.sleeveId);
              return (
                <div
                  key={f.id}
                  className="flex items-start gap-3 border-b border-line py-2.5 last:border-b-0"
                >
                  <span
                    className={`mt-0.5 grid h-[18px] w-[18px] flex-none place-items-center rounded-full font-mono text-[9px] font-semibold ${
                      f.side === 'buy'
                        ? s?.live
                          ? 'bg-fg text-canvas'
                          : 'bg-accent text-canvas'
                        : `border ${s?.live ? 'border-fg text-fg' : 'border-accent text-accent'}`
                    }`}
                  >
                    {f.side === 'buy' ? 'B' : 'S'}
                  </span>
                  <span className="min-w-0 text-[13px]">
                    {f.side === 'buy' ? 'Bought' : 'Sold'} {shares(f.qty)} at {f.price.toFixed(2)}
                    <span className="block text-[12px] text-fg-3">
                      {s?.name ?? 'Sleeve'} · {shortDate(f.at)}
                    </span>
                  </span>
                </div>
              );
            })}
          </>
        )}
      </aside>
    </div>
  );
}
