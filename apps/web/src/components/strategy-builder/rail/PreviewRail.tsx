import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
import { Check } from 'lucide-react';
import { useMemo } from 'react';

import {
  longestLookback,
  methodWords,
  rebalanceWord,
  strategySymbols,
  writtenScenarios,
} from '../../../lib/outline';
import { Pct } from '../../ui';
import type { EngineCheck } from '../hooks/useEngineCheck';
import type { RunningSession } from '../hooks/useRunningSession';
import { HOLDING_FILLS } from '../outline/holdingFills';

import { KeyValue, RailPanel } from './RailPanel';
import { sessionHoldings } from './sessionHoldings';
import { StackedBar } from './StackedBar';

interface PreviewRailProps {
  tree: StrategyTree;
  timeframe: string;
  benchmark: string;
  engine: EngineCheck;
  /** The last saved text and its version, shown when the draft can't be checked. */
  savedDsl: string | null;
  savedVersion: number;
  session: RunningSession | null;
  lastBacktest: { version: number; totalReturn: number } | null;
}

const fmtTime = (d: Date) =>
  d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

/** What the strategy holds as written, what it needs, and how it sits against its running session. */
export function PreviewRail({
  tree,
  timeframe,
  benchmark,
  engine,
  savedDsl,
  savedVersion,
  session,
  lastBacktest,
}: PreviewRailProps) {
  const draftBroken = engine.status === 'problems';
  const fallbackTree = useMemo(
    () => (draftBroken && savedDsl ? (fromDSLString(savedDsl)?.tree ?? null) : null),
    [draftBroken, savedDsl]
  );
  const shown = draftBroken ? fallbackTree : tree;
  const scenarios = useMemo(() => (shown ? writtenScenarios(shown) : []), [shown]);
  const symbols = useMemo(() => strategySymbols(tree), [tree]);
  const benchmarkOnly =
    benchmark && !symbols.held.includes(benchmark) && !symbols.signals.includes(benchmark)
      ? benchmark
      : null;
  const empty = scenarios.every((s) => s.holdings.length === 0);
  const lookback = useMemo(() => longestLookback(tree), [tree]);
  const held = useMemo(() => sessionHoldings(session?.positions ?? []), [session]);

  return (
    <div className="grid gap-4">
      <RailPanel
        title="Structural estimate"
        meta={
          draftBroken ? (fallbackTree ? `from version ${savedVersion}` : undefined) : 'as written'
        }
      >
        {draftBroken && !fallbackTree ? (
          <p className="m-0 text-[12.5px] text-fg-2">
            Fix the problems in the draft to see what it holds.
          </p>
        ) : empty ? (
          <p className="m-0 text-[12.5px] text-fg-2">Add a rule to see what it holds.</p>
        ) : (
          scenarios.map((s) => {
            const known = s.holdings.filter((h) => h.pct !== null);
            const ranked = s.holdings.filter((h) => h.pct === null);
            return (
              <div key={s.label} className="grid gap-2.5">
                {scenarios.length > 1 && <span className="kicker">{s.label}</span>}
                <StackedBar
                  label={s.label}
                  height={10}
                  segments={known.map((h, i) => ({
                    key: h.symbol,
                    pct: h.pct ?? 0,
                    fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
                  }))}
                />
                {known.length > 0 && (
                  <div>
                    {known.map((h, i) => (
                      <KeyValue
                        key={h.symbol}
                        k={
                          <span className="flex items-center">
                            <i
                              className="mr-2 inline-block h-2 w-2 rounded-[1px]"
                              style={{ background: HOLDING_FILLS[i % HOLDING_FILLS.length] }}
                            />
                            <b className="font-mono text-[12.5px] font-semibold text-fg">
                              {h.symbol}
                            </b>
                          </span>
                        }
                        v={<span className="num">{h.pct?.toFixed(1)}%</span>}
                      />
                    ))}
                  </div>
                )}
                {ranked.length > 0 && (
                  <p className="m-0 font-mono text-[12.5px] font-semibold leading-relaxed text-fg">
                    {ranked.map((h) => h.symbol).join(' ')}
                  </p>
                )}
                {s.rankedBy.length > 0 && (
                  <p className="m-0 text-[12px] text-fg-3">
                    {known.length > 0 ? 'The rest are ranked' : 'Ranked'} by{' '}
                    {s.rankedBy.map(methodWords).join(' and ')} at each rebalance.
                  </p>
                )}
              </div>
            );
          })
        )}
        <p className="m-0 text-[12px] leading-[1.55] text-fg-3">
          {draftBroken && fallbackTree
            ? 'The draft can’t be checked until its problems are fixed, so this shows the last saved version. '
            : ''}
          These are the weights as written. Weights at the last close, and which rule decided them,
          need an evaluation the engine doesn’t offer yet.
        </p>
      </RailPanel>

      {session?.session && (
        <RailPanel
          title="Against the paper session"
          meta={session.version ? `runs version ${session.version}` : undefined}
        >
          {held.holdings.length > 0 ? (
            <>
              <div className="flex items-baseline justify-between text-[12px]">
                <span className="text-fg-2">Holds now</span>
                {held.asOf && <span className="text-fg-3">as of {fmtTime(held.asOf)}</span>}
              </div>
              <StackedBar
                label="Session holdings"
                height={6}
                segments={held.holdings.map((h, i) => ({
                  key: h.symbol,
                  pct: h.pct,
                  fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
                }))}
              />
              <p className="m-0 font-mono text-[12px] text-fg-2">
                {held.holdings.map((h) => `${h.symbol} ${h.pct.toFixed(1)}%`).join(' · ')}
              </p>
            </>
          ) : (
            <p className="m-0 text-[12.5px] text-fg-2">The session holds no positions right now.</p>
          )}
          <p className="m-0 text-[12px] text-fg-3">
            What would trade at the next rebalance will appear once evaluation is available.
          </p>
        </RailPanel>
      )}

      <RailPanel title="What it needs">
        <div>
          <KeyValue
            k="Symbols"
            v={
              <span className="num">
                {symbols.held.length}
                {symbols.signals.length > 0 && ` · ${symbols.signals.join(' ')} as signal`}
                {benchmarkOnly && ` · ${benchmarkOnly} as benchmark`}
              </span>
            }
          />
          <KeyValue
            k="History before first rebalance"
            v={<span className="num">{lookback > 0 ? `${lookback} bars` : 'none'}</span>}
          />
          <KeyValue k="Rebalance" v={rebalanceWord(timeframe)} />
        </div>
      </RailPanel>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[12px]">
        <EngineChip engine={engine} />
        {lastBacktest && (
          <span className="text-fg-3">
            Last backtest, version {lastBacktest.version} ·{' '}
            <Pct value={lastBacktest.totalReturn} pnl dp={1} />
          </span>
        )}
      </div>
    </div>
  );
}

export function EngineChip({ engine }: { engine: EngineCheck }) {
  const count = engine.errors?.length ?? 0;
  const map = {
    idle: { cls: 'bg-sunk text-fg-2', text: 'Not checked yet' },
    checking: { cls: 'bg-sunk text-fg-2', text: 'Checking' },
    ok: { cls: 'bg-accent-soft text-accent', text: 'Valid' },
    problems: {
      cls: 'bg-risk-soft text-risk',
      text: `${count} ${count === 1 ? 'problem' : 'problems'}`,
    },
    unavailable: { cls: 'bg-sunk text-fg-2', text: 'Checks unavailable' },
  } as const;
  const m = map[engine.status];
  return (
    <span
      role="status"
      className={`inline-flex h-[21px] items-center gap-1.5 rounded-full px-2 text-[11px] font-medium ${m.cls}`}
    >
      {engine.status === 'ok' && <Check className="h-3 w-3" />}
      {m.text}
    </span>
  );
}
