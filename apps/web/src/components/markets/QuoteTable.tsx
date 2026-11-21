import { ArrowRight, ChevronDown, ChevronRight, Search, X } from 'lucide-react';
import { Fragment, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatNumber, moveTone, TONE_TEXT } from '../../lib/format';
import { nextRebalanceDate } from '../../lib/sessionState';
import { Sparkline } from '../charts';
import { etDayKey } from '../portfolio/history';
import { sleeveColor } from '../portfolio/sleeveView';
import { dayLabel } from '../sessions/sessionRows';
import { ModeBadge, Money } from '../ui';

import { cleanSymbol, shares, type Holder } from './marketsView';
import {
  fillPhrase,
  fillsOnDay,
  heldByText,
  nextSort,
  quoteRows,
  rangePosition,
  sortRows,
  type QuoteRow,
  type SortDir,
  type SortKey,
} from './quoteRows';
import { SymbolChart } from './SymbolChart';
import { findAsset, useQuoteExtras } from './useMarketData';
import type { MarketsModel } from './useMarketsModel';

const fullChart = (symbol: string) => `/markets?view=chart&symbol=${encodeURIComponent(symbol)}`;

function Change({ pct, className = '' }: { pct: number | null; className?: string }) {
  if (pct === null) return <span className={`num text-fg-3 ${className}`}>·</span>;
  return (
    <span className={`num ${TONE_TEXT[moveTone(pct)]} ${className}`}>
      {formatNumber(pct, { signed: true })}%
    </span>
  );
}

function RangeBar({ row }: { row: QuoteRow }) {
  const at = rangePosition(row.year, row.last);
  if (at === null || !row.year) return <span className="text-fg-3">·</span>;
  return (
    <span
      className="relative block h-1 w-[120px] rounded-[2px] bg-sunk shadow-[inset_0_0_0_1px_rgb(var(--line))]"
      title={`52 weeks: ${row.year.low.toFixed(2)} to ${row.year.high.toFixed(2)}`}
    >
      <i
        aria-hidden="true"
        className="absolute -top-[3px] h-2.5 w-0.5 rounded-[1px] bg-fg"
        style={{ left: `calc(${(at * 100).toFixed(1)}% - 1px)` }}
      />
      <span className="sr-only">
        {row.year.low.toFixed(2)} to {row.year.high.toFixed(2)}
      </span>
    </span>
  );
}

/** Ticker validation against Alpaca: there is no name search, so a ticker must be typed. */
export function AddSymbol({ m }: { m: MarketsModel }) {
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const s = cleanSymbol(query);
    if (!s) {
      setNote(query.trim() ? 'Type a ticker, like SPY.' : null);
      return;
    }
    if (m.heldSymbols.includes(s) || m.watching.includes(s)) {
      m.select(s);
      setQuery('');
      setNote(null);
      return;
    }
    setBusy(true);
    findAsset(s)
      .then((asset) => {
        if (!asset) {
          setNote(`Alpaca doesn't list ${s}.`);
          return;
        }
        m.watch([...m.watching, s]);
        m.select(s);
        setQuery('');
        setNote(null);
      })
      .catch(() => setNote(`${s} could not be checked with Alpaca. Please try again.`))
      .finally(() => setBusy(false));
  };

  return (
    <form onSubmit={onSubmit} className="relative w-full sm:w-[260px]">
      <Search
        aria-hidden="true"
        className="absolute left-3 top-[18px] h-4 w-4 -translate-y-1/2 text-fg-3"
      />
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setNote(null);
        }}
        placeholder="Add a symbol"
        aria-label="Add a symbol by its ticker"
        aria-describedby={note ? 'add-symbol-note' : undefined}
        disabled={busy}
        className="h-9 w-full rounded-full border border-line bg-sunk pl-9 pr-3 text-[13.5px] outline-none focus:border-accent"
      />
      {note && (
        <p id="add-symbol-note" role="status" className="m-0 mt-1.5 px-3 text-[12px] text-fg-2">
          {note}
        </p>
      )}
    </form>
  );
}

function HolderCard({ h, m }: { h: Holder; m: MarketsModel }) {
  const today = etDayKey(m.now);
  const fills = fillsOnDay(m.symbolFills, h.sleeveId, m.symbol, today, etDayKey);
  const next = h.running ? nextRebalanceDate(h.rebalance, m.today) : null;
  const rows: [string, ReactNode][] = [
    ['Shares, avg cost', `${shares(h.qty)} · ${h.avgCost.toFixed(2)}`],
    [
      'Weight',
      `${(h.weight * 100).toFixed(1)}%${h.target !== undefined ? ` of ${Math.round(h.target * 100)}%` : ''}`,
    ],
    ['Today', fills.length ? fills.map(fillPhrase).join(', ') : 'No fills today'],
    ['Next rebalance', next ? dayLabel(next) : h.running ? 'No fixed date' : 'Not running'],
  ];
  return (
    <section className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <i
          aria-hidden="true"
          className="h-2.5 w-2.5 flex-none rounded-[3px]"
          style={{ background: sleeveColor(h.index) }}
        />
        {h.sleeveId ? (
          <Link
            to={`/portfolio/sleeves/${h.sleeveId}`}
            className="truncate text-[13px] font-semibold hover:underline"
          >
            {h.name}
          </Link>
        ) : (
          <b className="truncate text-[13px] font-semibold">{h.name}</b>
        )}
        <ModeBadge mode={h.live ? 'live' : 'paper'} size="sm" />
        <span className="flex-1" />
        <Money value={h.marketValue} className="text-[13px]" />
      </div>
      <dl className="m-0">
        {rows.map(([k, v]) => (
          <div
            key={k}
            className="flex justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0"
          >
            <dt className="text-fg-2">{k}</dt>
            <dd className="num m-0 text-right">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Opened({ row, m, compact }: { row: QuoteRow; m: MarketsModel; compact: boolean }) {
  const chart = (
    <SymbolChart
      symbol={row.symbol}
      label={`${row.symbol} prices, ${m.rangeLabel}`}
      series={m.series}
      intraday={m.intraday}
      holders={row.holders}
      fills={m.fillMarks}
      height={compact ? 130 : 200}
      onRetry={m.retrySeries}
      costLabels={false}
    />
  );
  const open = (
    <Link to={fullChart(row.symbol)} className="btn btn-sm self-start">
      Open full chart
      <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
    </Link>
  );
  if (compact) {
    return (
      <div className="flex flex-col gap-2 pb-3">
        {chart}
        {open}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_330px] gap-5">
      <div className="min-w-0">{chart}</div>
      <div className="flex flex-col gap-4">
        {row.holders.length > 0 ? (
          row.holders.map((h) => <HolderCard key={h.executionId} h={h} m={m} />)
        ) : (
          <p className="m-0 text-[13px] text-fg-2">
            No sleeve holds {row.symbol}. A sleeve buys it only when its strategy includes it.
          </p>
        )}
        {open}
      </div>
    </div>
  );
}

const COLUMNS: {
  key: Exclude<SortKey, 'default'> | null;
  label: string;
  num?: boolean;
}[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: null, label: 'Name' },
  { key: 'last', label: 'Last', num: true },
  { key: 'change', label: 'Today', num: true },
  { key: null, label: 'Intraday' },
  { key: null, label: '52-week range' },
  { key: 'volume', label: 'Volume, IEX', num: true },
  { key: null, label: 'Held by' },
];

const TH =
  'whitespace-nowrap border-b border-line px-3 py-2.5 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3';
const TD = 'border-b border-line px-3 py-2 align-middle';

function useQuoteRows(m: MarketsModel): QuoteRow[] {
  const symbols = useMemo(() => [...m.heldSymbols, ...m.watchOnly], [m.heldSymbols, m.watchOnly]);
  const extras = useQuoteExtras(symbols);
  return useMemo(
    () =>
      quoteRows({
        held: m.held,
        watchOnly: m.watchOnly,
        quotes: m.quotes,
        names: extras.names,
        intraday: extras.intraday,
        years: extras.years,
      }),
    [m.held, m.watchOnly, m.quotes, extras]
  );
}

/** Markets as a quote table whose rows open in place (markets2 D). */
export function QuoteTable({ m, compact }: { m: MarketsModel; compact: boolean }) {
  const all = useQuoteRows(m);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: 'default',
    dir: 'asc',
  });
  const rows = useMemo(() => sortRows(all, sort.key, sort.dir), [all, sort]);
  const named = all.some((r) => r.name);
  const columns = named ? COLUMNS : COLUMNS.filter((c) => c.label !== 'Name');
  const pending = !m.loaded && (
    <p className="m-0 border-b border-line px-[18px] py-2.5 text-[12.5px] text-fg-3">
      Loading what your sleeves hold.
    </p>
  );
  const toggle = (symbol: string) => (m.opened === symbol ? m.close() : m.select(symbol));
  const unwatch = (symbol: string) => {
    m.watch(m.watching.filter((s) => s !== symbol));
    if (m.opened === symbol) m.close();
  };

  if (rows.length === 0) {
    return (
      <div className="panel px-5 py-6 text-[13px] text-fg-2">
        {m.loaded ? 'Add a symbol to see its price here.' : 'Loading your holdings.'}
      </div>
    );
  }

  if (compact) {
    return (
      <div className="panel px-4">
        {pending}
        {rows.map((r) => {
          const open = m.opened === r.symbol;
          return (
            <Fragment key={r.symbol}>
              <button
                type="button"
                onClick={() => toggle(r.symbol)}
                aria-expanded={open}
                className="flex w-full items-center gap-3 border-b border-line py-[11px] text-left text-[14.5px] last:border-b-0"
              >
                <span className="w-11 flex-none font-mono text-[13px] font-semibold">
                  {r.symbol}
                </span>
                <span
                  className={`min-w-0 flex-1 truncate text-[12.5px] ${r.held ? 'text-fg-2' : 'text-fg-3'}`}
                >
                  {r.held ? heldByText(r.holders) : 'Watching'}
                </span>
                <span className="flex-none text-right">
                  <span className="num block">{r.last !== null ? r.last.toFixed(2) : '·'}</span>
                  <Change pct={r.changePct} className="block text-[12px]" />
                </span>
              </button>
              {open && <Opened row={r} m={m} compact />}
            </Fragment>
          );
        })}
      </div>
    );
  }

  return (
    <div className="panel overflow-x-auto">
      {pending}
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th className={`${TH} w-5 pl-[18px]`}>
              <span className="sr-only">Open</span>
            </th>
            {columns.map((c) => {
              const key = c.key;
              const active = key !== null && sort.key === key;
              return (
                <th
                  key={c.label}
                  className={`${TH} ${c.num ? 'text-right' : ''} last:pr-[18px]`}
                  aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {key ? (
                    <button
                      type="button"
                      onClick={() => setSort((s) => nextSort(s, key))}
                      className={`uppercase tracking-[0.06em] hover:text-fg ${active ? 'text-fg' : ''}`}
                    >
                      {c.label}
                      {active && (sort.dir === 'asc' ? ' ↑' : ' ↓')}
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const open = m.opened === r.symbol;
            const Chevron = open ? ChevronDown : ChevronRight;
            return (
              <Fragment key={r.symbol}>
                <tr
                  onClick={() => toggle(r.symbol)}
                  className={`cursor-pointer ${open ? 'bg-accent/10' : 'hover:bg-sunk/60'}`}
                >
                  <td className={`${TD} w-5 pl-[18px] text-fg-3`}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggle(r.symbol);
                      }}
                      aria-expanded={open}
                      aria-controls={`quote-${r.symbol}`}
                      aria-label={`${open ? 'Close' : 'Open'} ${r.symbol}`}
                      className="grid h-5 w-5 place-items-center rounded hover:text-fg"
                    >
                      <Chevron className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </td>
                  <td className={TD}>
                    <span className="font-mono font-semibold">{r.symbol}</span>
                  </td>
                  {named && (
                    <td className={`${TD} max-w-[260px] truncate text-[12.5px] text-fg-2`}>
                      {r.name || <span className="text-fg-3">·</span>}
                    </td>
                  )}
                  <td className={`${TD} num text-right`}>
                    {r.last !== null ? r.last.toFixed(2) : '·'}
                  </td>
                  <td className={`${TD} text-right`}>
                    <Change pct={r.changePct} />
                  </td>
                  <td className={TD}>
                    {r.intraday.length > 1 ? (
                      <Sparkline
                        values={r.intraday}
                        width={90}
                        height={22}
                        tone="accent"
                        label={`${r.symbol} today`}
                      />
                    ) : (
                      <span className="text-fg-3">·</span>
                    )}
                  </td>
                  <td className={TD}>
                    <RangeBar row={r} />
                  </td>
                  <td className={`${TD} num text-right text-fg-3`}>
                    {r.volume !== null ? formatNumber(r.volume, { dp: 0 }) : '·'}
                  </td>
                  <td className={`${TD} pr-[18px] text-[12.5px]`}>
                    {r.held ? (
                      heldByText(r.holders)
                    ) : (
                      <span className="inline-flex items-center gap-2 text-fg-3">
                        Watching
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            unwatch(r.symbol);
                          }}
                          aria-label={`Stop watching ${r.symbol}`}
                          className="grid h-5 w-5 place-items-center rounded hover:text-fg"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
                {open && (
                  <tr id={`quote-${r.symbol}`}>
                    <td
                      colSpan={columns.length + 1}
                      className="border-b border-line bg-sunk/55 px-[18px] py-3.5"
                    >
                      <Opened row={r} m={m} compact={false} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <p className="m-0 border-t border-line px-[18px] py-2.5 text-[11.5px] text-fg-3">
        Volume is what Alpaca&apos;s IEX feed saw, which is part of market volume. Watched symbols
        are kept in this browser.
      </p>
    </div>
  );
}
