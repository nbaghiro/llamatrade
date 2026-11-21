import { fixedTargets } from '@llamatrade/core/agent/structure';
import { marketDataClient } from '@llamatrade/core/net';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import { toDate, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { barsToCandles } from '@llamatrade/core/stores/markets';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { ArrowRightLeft, Briefcase, ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

import { Panel } from '../../components/backtest/parts';
import { AnnotatedCurve } from '../../components/charts';
import { buildSessionRow } from '../../components/sessions';
import {
  buildRebalanceDiff,
  closesOn,
  untradedSymbols,
  type RebalanceDiff,
} from '../../components/sessions/rebalanceDiff';
import {
  RebalanceHunks,
  RebalanceHunksCompact,
  type DiffView,
} from '../../components/sessions/RebalanceHunks';
import {
  etDayLabel,
  etHm,
  fillDays,
  toSeries,
  windowed,
  type FillDay,
} from '../../components/sessions/timeline';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { ModeBadge, PageHead, Segmented } from '../../components/ui';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart } from '../../components/ui/Skeleton';
import { formatMoney } from '../../lib/format';

const DAY_MS = 86_400_000;
const VIEWS: readonly { key: DiffView; label: string }[] = [
  { key: 'split', label: 'Split' },
  { key: 'unified', label: 'Unified' },
];

const stamp = (d: Date) => `${etDayLabel(d)}, ${etHm(d)}`;
const ts = (ms: number) => ({ seconds: BigInt(Math.floor(ms / 1000)), nanos: 0 });

interface Closes {
  key: string;
  closes: Record<string, number>;
}

/** That day's close for each holding the rebalance didn't trade, so it can be valued. */
function useCloses(day: FillDay | null, symbols: readonly string[]): Closes | null {
  const key = day ? `${day.key}:${symbols.join(',')}` : '';
  const [state, setState] = useState<Closes | null>(null);
  useEffect(() => {
    if (!day || symbols.length === 0) return;
    let live = true;
    const at = day.at.getTime();
    marketDataClient
      .getMultiBars({
        symbols: [...symbols],
        start: ts(at - 2 * DAY_MS),
        end: ts(at + 2 * DAY_MS),
        timeframe: Timeframe.TIMEFRAME_1DAY,
        limit: 0,
      })
      .then((res) => {
        const bars: Record<string, { time: number; close: number }[]> = {};
        for (const s of symbols) bars[s] = barsToCandles(res.bars[s]?.bars ?? []);
        if (live) setState({ key, closes: closesOn(bars, day.key) });
      })
      .catch(() => {
        if (live) setState({ key, closes: {} });
      });
    return () => {
      live = false;
    };
  }, [key, day, symbols]);
  if (!day) return null;
  if (symbols.length === 0) return { key, closes: {} };
  return state?.key === key ? state : null;
}

function FileLink({
  href,
  icon,
  label,
  count,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  count: string;
}) {
  return (
    <a
      href={href}
      className="flex items-center gap-2 rounded-[6px] px-2.5 py-1.5 text-[13px] text-fg-2 hover:bg-sunk hover:text-fg"
    >
      {icon}
      {label}
      <span className="ml-auto font-mono text-[11px] text-fg-3">{count}</span>
    </a>
  );
}

function Sidebar({ diff }: { diff: RebalanceDiff }) {
  const holdingsCount =
    diff.added + diff.removed > 0
      ? `${diff.added ? `+${diff.added}` : ''}${diff.added && diff.removed ? ' ' : ''}${diff.removed ? `−${diff.removed}` : ''}`
      : '0';
  return (
    <div className="flex flex-col gap-3.5">
      <nav aria-label="Changes" className="panel p-1.5">
        <FileLink
          href="#holdings"
          icon={<Briefcase className="h-3.5 w-3.5" aria-hidden="true" />}
          label="Holdings"
          count={holdingsCount}
        />
        <FileLink
          href="#orders"
          icon={<ArrowRightLeft className="h-3.5 w-3.5" aria-hidden="true" />}
          label="Orders"
          count={String(diff.ordersFilled)}
        />
      </nav>
      <div className="panel px-3.5 py-3">
        <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
          Holdings value
        </div>
        <div className="mt-1 font-mono text-[14px] font-semibold">
          {diff.valueBefore !== null && diff.valueAfter !== null ? (
            <>
              <span className="text-fg-3">{formatMoney(diff.valueBefore)}</span> →{' '}
              {formatMoney(diff.valueAfter)}
            </>
          ) : (
            '·'
          )}
        </div>
        <div className="mt-1 text-[11.5px] text-fg-3">
          {diff.valueBefore !== null
            ? 'At the same prices before and after, cash not counted'
            : "A holding's price on this day isn't recorded"}
        </div>
      </div>
      <p className="m-0 px-1 text-[12px] leading-relaxed text-fg-3">
        The engine doesn&apos;t record which rule ran or the inputs it read yet, so those
        aren&apos;t part of this diff.
      </p>
    </div>
  );
}

/**
 * /trading/:sessionId/rebalances: each rebalance that traded, opened as a change set against the
 * one before it (rebalance2 D). Shares come from fills; rule branch and inputs aren't stored.
 */
export default function RebalancesPage() {
  const { sessionId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<DiffView>('split');
  const compact = useMediaQuery('(max-width: 767px)');
  const detail = useTradingStore((s) => (s.detail?.session.id === sessionId ? s.detail : null));
  const detailError = useTradingStore((s) => s.detailError);
  const detailLoading = useTradingStore((s) => s.detailLoading);
  const loadSession = useTradingStore((s) => s.loadSession);
  const performance = useTradingStore((s) => s.performance);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);

  useEffect(() => {
    loadSession(sessionId, new Date(0)).catch(() => undefined);
    fetchStrategies().catch(() => undefined);
  }, [sessionId, loadSession, fetchStrategies]);

  const row = useMemo(
    () =>
      detail
        ? buildSessionRow(detail.session, {
            executions: detail.execution ? [detail.execution] : [],
            sleeves: detail.sleeve ? [detail.sleeve] : [],
            performance: detail.performance ? [detail.performance] : performance,
            strategies,
            orders: detail.orders,
          })
        : null,
    [detail, performance, strategies]
  );

  const orders = useMemo(() => detail?.orders ?? [], [detail]);
  const days = useMemo(() => fillDays(orders), [orders]);
  const wanted = params.get('day');
  const found = wanted ? days.findIndex((d) => d.key === wanted) : -1;
  const index = found >= 0 ? found : days.length - 1;
  const day = days[index] ?? null;
  const untraded = useMemo(() => (day ? untradedSymbols(orders, day) : []), [orders, day]);
  const closes = useCloses(day, untraded);

  const targets = useMemo(() => {
    const strategy = strategies.find((s) => s.id === detail?.session.strategyId);
    return strategy && detail?.execution && strategy.version === detail.execution.version
      ? fixedTargets(strategy.dslCode)
      : null;
  }, [strategies, detail]);
  const diff = useMemo(
    () => (closes ? buildRebalanceDiff(orders, days, index, closes.closes, targets) : null),
    [orders, days, index, closes, targets]
  );

  if (detailError && !detail) {
    return (
      <div className="page">
        <PageHead crumbs={[{ label: 'Sessions', to: '/trading' }]} title="Rebalances" />
        <Panel>
          <PanelError
            title="This session couldn't be loaded"
            cause={detailError}
            onRetry={() => loadSession(sessionId, new Date(0))}
            retrying={detailLoading}
          />
        </Panel>
      </div>
    );
  }
  if (!detail || !row) {
    return (
      <div className="page" aria-busy="true">
        <SkeletonChart height={300} />
      </div>
    );
  }

  const { session } = detail;
  const mode = session.mode === ExecutionMode.LIVE ? 'live' : 'paper';
  const now = new Date();
  const started = toDate(session.startedAt);
  const ended = row.view.open ? null : toDate(session.endedAt);
  const end = ended ?? now;
  const start = started ?? new Date(end.getTime() - 90 * DAY_MS);
  const series = windowed(
    toSeries(detail.curve),
    start,
    end,
    row.view.open ? row.figures.equity : null
  );
  const select = (i: number) => {
    const d = days[i];
    if (!d) return;
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        n.set('day', d.key);
        return n;
      },
      { replace: true }
    );
  };

  const title = day
    ? index > 0
      ? compact
        ? `${etDayLabel(days[index - 1].at)} → ${etDayLabel(day.at)}`
        : `${stamp(days[index - 1].at)} → ${stamp(day.at)}`
      : stamp(day.at)
    : 'Rebalances';
  const sub = !day
    ? 'Nothing has traded yet. Each rebalance that places orders appears here as a diff.'
    : diff
      ? `${diff.changes} ${diff.changes === 1 ? 'change' : 'changes'} · ${diff.ordersFilled} ${
          diff.ordersFilled === 1 ? 'order' : 'orders'
        } filled · ${
          index > 0
            ? 'comparing with the last rebalance that traded'
            : 'the first rebalance that traded'
        }`
      : 'Loading the prices for this rebalance';

  return (
    <div className="page">
      <PageHead
        crumbs={[
          { label: 'Sessions', to: '/trading' },
          { label: row.name, to: `/trading/${sessionId}` },
          { label: 'Rebalances' },
        ]}
        title={title}
        documentTitle={`Rebalances · ${row.name}`}
        badges={<ModeBadge mode={mode} />}
        sub={sub}
        actions={
          day ? (
            <>
              {!compact && (
                <Segmented label="Diff view" options={VIEWS} value={view} onChange={setView} />
              )}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={index <= 0}
                onClick={() => select(index - 1)}
              >
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                Older
              </button>
              {index < days.length - 1 && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => select(index + 1)}
                >
                  Newer
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              )}
            </>
          ) : undefined
        }
      />

      {days.length > 0 && (
        <div className="panel-rim mb-3.5 px-5 pb-3 pt-3">
          {series.dates.length > 1 && !compact && (
            <AnnotatedCurve
              label={`${row.name} sleeve value with its rebalances`}
              dates={series.dates}
              values={series.values}
              start={start}
              end={end}
              height={96}
              now={row.view.open ? { label: `Now ${etHm(now)}` } : undefined}
              pins={day ? [{ at: day.at, label: etDayLabel(day.at), tone: 'accent' }] : []}
              lanes={[
                {
                  id: 'rebalances',
                  label: 'Rebalances',
                  sub: `${days.length} traded`,
                  events: days.map((d, i) => ({
                    at: d.at,
                    shape: i === index ? ('dot' as const) : ('ring' as const),
                    count: i === index ? d.orders.length : undefined,
                    title: `${etDayLabel(d.at)}: ${d.orders.length} ${d.orders.length === 1 ? 'order' : 'orders'}`,
                  })),
                },
              ]}
            />
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11.5px] text-fg-3">
              {days.length} {days.length === 1 ? 'rebalance' : 'rebalances'} traded
              {started ? ` since ${etDayLabel(started)}` : ''}. Checks that placed no orders
              aren&apos;t recorded.
            </span>
            {days.map((d, i) => (
              <button
                key={d.key}
                type="button"
                onClick={() => select(i)}
                aria-pressed={i === index}
                className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] ${
                  i === index
                    ? 'border-accent bg-accent-soft text-fg'
                    : 'border-line text-fg-2 hover:text-fg'
                }`}
              >
                {etDayLabel(d.at)}
              </button>
            ))}
          </div>
        </div>
      )}

      {day &&
        (!diff ? (
          <SkeletonChart height={220} />
        ) : compact ? (
          <RebalanceHunksCompact diff={diff} />
        ) : (
          <div className="grid items-start gap-[18px] lg:grid-cols-[220px_minmax(0,1fr)]">
            <Sidebar diff={diff} />
            <RebalanceHunks diff={diff} view={view} />
          </div>
        ))}
    </div>
  );
}
