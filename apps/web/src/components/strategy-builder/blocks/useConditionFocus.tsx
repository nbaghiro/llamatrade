import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import { toDate, toNumber, toTimestamp } from '@llamatrade/core/stores/backtest';
import {
  conditionStats,
  indicatorFromCloses,
  isDrawableIndicator,
  warmupBars,
  type ConditionStats,
} from '@llamatrade/core/strategy/indicators';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import {
  COMPARATORS,
  INDICATORS,
  type Comparator,
  type ConditionExpression,
  type IfBlock,
  type IndicatorName,
  type PriceField,
} from '@llamatrade/core/strategy/types';
import { Info, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import {
  comparatorPhrase,
  indicatorLabel,
  isValidSymbol,
  normaliseSymbol,
} from '../../../lib/outline';
import { matchBlocks } from '../../../lib/strategyDiff';
import { marketDataClient } from '../../../services/grpc-client';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { PanelError, SkeletonChart } from '../../ui';
import { KeyValue, RailPanel } from '../rail/RailPanel';

import {
  changeSentence,
  drawableOf,
  fmt,
  monthYear,
  rebalanceEvery,
  rebalanceIndexes,
  shortDay,
  type Drawable,
  type RebalanceEvery,
} from './conditionHistory';
import { CommitInput, Field } from './fields';
import { CHART_H, ThresholdChart, type History } from './ThresholdChart';

const WINDOW_BARS = 504;

type Load =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; history: History };

const PRICE_FIELD: Record<PriceField, 'open' | 'high' | 'low' | 'close' | 'volume'> = {
  current: 'close',
  close: 'close',
  open: 'open',
  high: 'high',
  low: 'low',
  volume: 'volume',
};

const EXPLAIN: Partial<Record<IndicatorName, string>> = {
  rsi: 'RSI compares recent gains with recent losses on a 0 to 100 scale. Readings above 70 are often called overbought.',
  sma: 'A simple moving average is the mean close over the period.',
  ema: 'An exponential moving average weights recent closes more than older ones.',
  momentum: 'Momentum here is the close minus the close the given number of days earlier.',
};

function drawKey(d: Drawable | null): string {
  if (!d) return '';
  return d.kind === 'indicator'
    ? `i|${d.symbol}|${d.indicator}|${d.period}`
    : `p|${d.symbol}|${d.field}`;
}

function canDraw(d: Drawable | null): boolean {
  if (!d) return false;
  return d.kind === 'price' || isDrawableIndicator(d.indicator as IndicatorName);
}

/** Loads two years of the left operand's daily values, plus warm-up for the indicator. */
function useOperandHistory(drawable: Drawable | null, retry: number): Load {
  const [load, setLoad] = useState<Load>({ state: 'idle' });
  const key = drawKey(drawable);
  const drawableRef = useRef(drawable);
  drawableRef.current = drawable;

  useEffect(() => {
    const d = drawableRef.current;
    if (!d || !canDraw(d)) {
      setLoad({ state: 'idle' });
      return;
    }
    let live = true;
    setLoad({ state: 'loading' });
    const warm =
      d.kind === 'indicator' && isDrawableIndicator(d.indicator as IndicatorName)
        ? warmupBars(d.indicator as Parameters<typeof warmupBars>[0], d.period)
        : 0;
    const bars = WINDOW_BARS + warm + 5;
    const end = new Date();
    const start = new Date(end.getTime() - Math.ceil(bars * 1.5 + 10) * 86_400_000);
    marketDataClient
      .getHistoricalBars({
        symbol: d.symbol,
        timeframe: Timeframe.TIMEFRAME_1DAY,
        start: toTimestamp(start),
        end: toTimestamp(end),
        adjustForSplits: true,
        pagination: { page: 1, pageSize: Math.min(5000, bars + 200) },
      })
      .then((res) => {
        if (!live) return;
        const dates: Date[] = [];
        const raw: number[] = [];
        const closes: number[] = [];
        const field = d.kind === 'price' ? PRICE_FIELD[d.field] : 'close';
        for (const b of res.bars) {
          const at = toDate(b.timestamp);
          if (!at) continue;
          dates.push(at);
          closes.push(toNumber(b.close));
          raw.push(field === 'volume' ? Number(b.volume) : toNumber(b[field]));
        }
        const series =
          d.kind === 'indicator' && isDrawableIndicator(d.indicator as IndicatorName)
            ? indicatorFromCloses(
                d.indicator as Parameters<typeof indicatorFromCloses>[0],
                closes,
                d.period
              )
            : raw;
        const from = Math.max(0, dates.length - WINDOW_BARS);
        setLoad({
          state: 'ready',
          history: {
            dates: dates.slice(from),
            values: series.slice(from),
            lastClose: series.length ? series[series.length - 1] : null,
          },
        });
      })
      .catch((err: unknown) => {
        if (!live) return;
        setLoad({
          state: 'error',
          message: err instanceof Error ? err.message : 'The request failed.',
        });
      });
    return () => {
      live = false;
    };
  }, [key, retry]);

  return load;
}

const EVERY_LABEL: Record<RebalanceEvery, string> = {
  daily: 'Daily rebalances',
  weekly: 'Weekly rebalances',
  monthly: 'Monthly rebalances',
  quarterly: 'Quarterly rebalances',
  annually: 'Yearly rebalances',
};

/**
 * The condition of an if block opened under its rule (condition2 A): its fields, and the
 * left side's daily history with the threshold as a line to drag. Returns null unless
 * `blockId` is an if block.
 */
export function useConditionFocus(
  blockId: string | null,
  onClose: () => void
): { inline: ReactNode; rail: ReactNode } | null {
  const { tree, savedDsl, serverVersion, timeframe, updateCondition } =
    useStrategyBuilderStoreWithContext();
  const block = blockId ? tree.blocks[blockId] : undefined;
  const ifBlock: IfBlock | null = block?.type === 'if' ? block : null;
  const condition = ifBlock?.condition ?? null;
  const drawable = useMemo(() => (condition ? drawableOf(condition) : null), [condition]);

  const [retry, setRetry] = useState(0);
  const load = useOperandHistory(drawable, retry);

  const [live, setLive] = useState<number | null>(null);
  useEffect(() => setLive(null), [blockId, drawable?.threshold]);
  const threshold = live ?? drawable?.threshold ?? 0;

  const savedThreshold = useMemo(() => {
    if (!savedDsl || !ifBlock) return null;
    const saved = fromDSLString(savedDsl);
    if (!saved) return null;
    const beforeId = matchBlocks(saved.tree, tree).get(ifBlock.id);
    const before = beforeId ? saved.tree.blocks[beforeId] : undefined;
    if (before?.type !== 'if') return null;
    const was = drawableOf(before.condition);
    if (!was || !drawable || drawKey(was) !== drawKey(drawable)) return null;
    return was.threshold;
  }, [savedDsl, ifBlock, tree, drawable]);

  const every = rebalanceEvery(timeframe);
  const history = load.state === 'ready' ? load.history : null;
  const comparator: Comparator = condition?.comparator ?? 'gt';
  const rebalances = useMemo(
    () => (history ? rebalanceIndexes(history.dates, every) : []),
    [history, every]
  );
  const stats = useMemo(
    () => (history ? conditionStats(history.values, comparator, threshold, rebalances) : null),
    [history, comparator, threshold, rebalances]
  );
  const savedStats = useMemo(
    () =>
      history && savedThreshold !== null
        ? conditionStats(history.values, comparator, savedThreshold, rebalances)
        : null,
    [history, comparator, savedThreshold, rebalances]
  );

  const update = useCallback(
    (next: ConditionExpression) => {
      if (ifBlock) updateCondition(ifBlock.id, next);
    },
    [ifBlock, updateCondition]
  );

  const commitThreshold = useCallback(
    (value: number) => {
      if (!condition || condition.right.type !== 'number') return;
      const rounded = Math.round(value * 100) / 100;
      update({ ...condition, right: { ...condition.right, value: rounded } });
    },
    [condition, update]
  );

  if (!ifBlock || !condition) return null;

  const left = condition.left;
  const right = condition.right;
  const drawableNow = canDraw(drawable);
  const savedLabel = `v${serverVersion}`;
  const symbol = left.type === 'number' ? '' : left.symbol;
  const seriesName =
    left.type === 'indicator'
      ? `${symbol}'s ${left.period ? `${left.period}-day ` : ''}${indicatorLabel(left.indicator)}`
      : left.type === 'price'
        ? `${symbol}'s ${PRICE_FIELD[left.field]}`
        : symbol;

  const setSymbol = (raw: string): string | null => {
    if (left.type === 'number') return null;
    if (!isValidSymbol(raw)) return 'Enter a ticker, for example SPY.';
    update({ ...condition, left: { ...left, symbol: normaliseSymbol(raw) } });
    return null;
  };
  const setPeriod = (raw: string): string | null => {
    const v = Number(raw);
    if (!Number.isInteger(v) || v < 1 || v > 2520) return 'Use a whole number of days, 1 to 2520.';
    if (left.type === 'indicator' || left.type === 'metric') {
      update({ ...condition, left: { ...left, period: v } });
    }
    return null;
  };
  const setThreshold = (raw: string): string | null => {
    const v = Number(raw.trim());
    if (raw.trim() === '' || !Number.isFinite(v)) return 'Enter a number.';
    setLive(null);
    commitThreshold(v);
    return null;
  };

  const select = 'input h-9 pr-8';
  const inline = (
    <section
      aria-label="Edit the condition"
      className="mb-3 mt-1 grid gap-4 rounded-panel border border-accent/50 bg-panel px-4 py-4 shadow-[0_0_0_3px_var(--accent-soft)]"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-start gap-3">
        <div className="grid min-w-0 flex-1 grid-cols-2 gap-3 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,0.8fr)_minmax(0,1.1fr)_minmax(0,1fr)]">
          {left.type === 'indicator' && (
            <Field label="Indicator">
              <select
                className={select}
                value={left.indicator}
                onChange={(e) =>
                  update({
                    ...condition,
                    left: { ...left, indicator: e.target.value as IndicatorName },
                  })
                }
              >
                {INDICATORS.map((i) => (
                  <option key={i.name} value={i.name}>
                    {i.shortLabel}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {left.type === 'price' && (
            <Field label="Price">
              <select
                className={select}
                value={left.field}
                onChange={(e) =>
                  update({ ...condition, left: { ...left, field: e.target.value as PriceField } })
                }
              >
                {(Object.keys(PRICE_FIELD) as PriceField[]).map((f) => (
                  <option key={f} value={f}>
                    {f === 'current' ? 'price' : f}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {left.type !== 'number' && (
            <Field label="Symbol">
              <CommitInput ariaLabel="Symbol" value={left.symbol} onCommit={setSymbol} />
            </Field>
          )}
          {(left.type === 'indicator' || left.type === 'metric') && left.period != null && (
            <Field label="Period">
              <CommitInput
                ariaLabel="Period"
                value={String(left.period)}
                onCommit={setPeriod}
                inputMode="numeric"
                suffix="days"
              />
            </Field>
          )}
          <Field label="Comparison">
            <select
              className={select}
              value={condition.comparator}
              onChange={(e) => update({ ...condition, comparator: e.target.value as Comparator })}
            >
              {COMPARATORS.map((c) => (
                <option key={c.value} value={c.value}>
                  {comparatorPhrase(c.value)}
                </option>
              ))}
            </select>
          </Field>
          {right.type === 'number' && (
            <Field label="Threshold">
              <CommitInput
                ariaLabel="Threshold"
                value={String(live !== null ? Math.round(live * 100) / 100 : right.value)}
                onCommit={setThreshold}
                inputMode="decimal"
              />
            </Field>
          )}
        </div>
        <div className="hidden flex-none text-right font-mono text-[11.5px] text-fg-3 sm:block">
          {history?.lastClose != null && Number.isFinite(history.lastClose) && (
            <>
              <div>Last close: {fmt(history.lastClose)}</div>
              <div>{shortDay(history.dates[history.dates.length - 1])}</div>
            </>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the condition"
          className="grid h-7 w-7 flex-none place-items-center rounded-[6px] text-fg-3 hover:bg-sunk hover:text-fg"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {!drawable ? (
        <p className="m-0 text-[12.5px] text-fg-2">
          The history line needs one series compared with a number, so it isn’t drawn for this
          condition.
        </p>
      ) : !drawableNow ? (
        <p className="m-0 text-[12.5px] text-fg-2">
          This indicator’s history isn’t drawn here yet.
        </p>
      ) : load.state === 'loading' || load.state === 'idle' ? (
        <SkeletonChart height={CHART_H + 40} />
      ) : load.state === 'error' ? (
        <PanelError
          title={`${symbol}’s history couldn’t be loaded`}
          cause={load.message}
          unaffected="The condition can still be edited and saved."
          onRetry={() => setRetry((r) => r + 1)}
        />
      ) : history && history.values.length > 1 && stats ? (
        <>
          <ThresholdChart
            history={history}
            threshold={threshold}
            saved={savedThreshold}
            savedLabel={savedLabel}
            stats={stats}
            savedStats={savedStats}
            rebalances={rebalances}
            every={every}
            onDrag={(v) => setLive(v)}
            onRelease={() => {
              if (live !== null) commitThreshold(live);
            }}
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-fg-2">
            {every !== 'daily' && (
              <>
                <span className="flex items-center gap-1.5">
                  <i className="inline-block h-2.5 w-2.5 rounded-full border-[1.5px] border-accent" />
                  Rebalance where {fmt(threshold)} picks the When side
                </span>
                {savedStats && savedThreshold !== threshold && (
                  <span className="flex items-center gap-1.5">
                    <i className="inline-block h-2.5 w-2.5 rounded-full border border-dashed border-fg-3" />
                    Only at {fmt(savedThreshold ?? 0)}
                  </span>
                )}
              </>
            )}
            <span className="text-fg-3 sm:ml-auto">
              Drag the line or type a value. Nothing is saved until you save the version.
            </span>
          </div>
        </>
      ) : (
        <p className="m-0 text-[12.5px] text-fg-2">
          There isn’t enough daily history for {symbol} to draw this yet.
        </p>
      )}
    </section>
  );

  const showSaved = savedStats !== null && savedThreshold !== null && savedThreshold !== threshold;
  const twoColumns = savedStats !== null && savedThreshold !== null;
  const rail = (
    <div className="grid gap-4">
      <RailPanel
        title="How often it held"
        meta={
          history && history.dates.length
            ? `${monthYear(history.dates[0])} to ${monthYear(history.dates[history.dates.length - 1])}`
            : undefined
        }
      >
        {stats ? (
          <div>
            {twoColumns && (
              <div className="grid grid-cols-[minmax(0,1fr)_72px_72px] pb-1 text-right font-mono text-[10.5px] uppercase tracking-[0.06em] text-fg-3">
                <span />
                <span>
                  At {fmt(savedThreshold ?? 0)} · {savedLabel}
                </span>
                <span>At {fmt(threshold)}</span>
              </div>
            )}
            {(
              [
                ['Trading days', (s: ConditionStats) => String(s.days)],
                ['Separate stretches', (s: ConditionStats) => String(s.stretches.length)],
                ...(every === 'daily'
                  ? []
                  : ([
                      [
                        EVERY_LABEL[every],
                        (s: ConditionStats) => `${s.rebalancesHeld.length} of ${rebalances.length}`,
                      ],
                    ] as const)),
              ] as ReadonlyArray<readonly [string, (s: ConditionStats) => string]>
            ).map(([label, pick]) =>
              twoColumns && savedStats ? (
                <div
                  key={label}
                  className="grid grid-cols-[minmax(0,1fr)_72px_72px] border-b border-line py-2 text-[12.5px] last:border-b-0"
                >
                  <span className="text-fg-2">{label}</span>
                  <span className="num text-right text-fg-2">{pick(savedStats)}</span>
                  <span className="num text-right font-semibold text-fg">{pick(stats)}</span>
                </div>
              ) : (
                <KeyValue key={label} k={label} v={<span className="num">{pick(stats)}</span>} />
              )
            )}
          </div>
        ) : (
          <p className="m-0 text-[12.5px] text-fg-2">
            {drawableNow
              ? 'The counts appear once the history loads.'
              : 'Counts need a history the editor can draw.'}
          </p>
        )}
      </RailPanel>

      {stats && (
        <RailPanel title="What changes">
          <p className="m-0 text-[12.5px] leading-[1.55] text-fg">
            {changeSentence({
              threshold: fmt(threshold),
              days: stats.days,
              rebalances: stats.rebalancesHeld.length,
              total: rebalances.length,
              every,
              saved:
                showSaved && savedStats
                  ? { days: savedStats.days, rebalances: savedStats.rebalancesHeld.length }
                  : null,
            })}
          </p>
          <p className="m-0 text-[12px] leading-[1.55] text-fg-3">
            These counts come from {seriesName} on daily closes, not a backtest. Returns need a
            backtest of the saved version.
          </p>
        </RailPanel>
      )}

      {left.type === 'indicator' && EXPLAIN[left.indicator] && (
        <div className="grid grid-cols-[16px_minmax(0,1fr)] gap-2.5 rounded-panel bg-sunk px-4 py-3 text-[12.5px] text-fg-2">
          <Info className="mt-0.5 h-4 w-4 text-fg-3" aria-hidden="true" />
          <span>{EXPLAIN[left.indicator]}</span>
        </div>
      )}
    </div>
  );

  return { inline, rail };
}
