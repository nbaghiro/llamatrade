import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { BlockId, WeightBlock, WeightMethod } from '@llamatrade/core/strategy/types';
import { Lock, Unlock, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { methodUsesLookback, methodWords } from '../../../lib/outline';
import { matchBlocks } from '../../../lib/strategyDiff';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { Money } from '../../ui';
import { HOLDING_FILLS } from '../outline/holdingFills';
import { KeyValue, RailPanel } from '../rail/RailPanel';
import { StackedBar } from '../rail/StackedBar';

import { NumberCell } from './fields';
import { AddSymbol, WeightBar } from './WeightBar';
import {
  knownWeights,
  rowOf,
  setWeight,
  shareOfWhole,
  splitEvenly,
  total,
  type WeightRow,
} from './weightMath';

interface MethodCard {
  method: WeightMethod;
  code: string;
  hint: string;
}

const METHODS: readonly MethodCard[] = [
  { method: 'specified', code: 'specified', hint: 'Weights you set' },
  { method: 'equal', code: 'equal', hint: 'Same for each' },
  { method: 'inverse_volatility', code: 'inverse-volatility', hint: 'Calmer gets more' },
  { method: 'risk_parity', code: 'risk-parity', hint: 'Equal risk share' },
  { method: 'min_variance', code: 'min-variance', hint: 'Lowest combined swing' },
  { method: 'momentum', code: 'momentum', hint: 'Stronger gets more' },
  { method: 'market_cap', code: 'market-cap', hint: 'Not available' },
];

/**
 * How a weight block splits its share (weights2 A): the method, and for fixed weights one
 * bar to drag with rows to type in. Returns null unless `blockId` is a weight block.
 */
export function useWeightsFocus(
  blockId: string | null,
  onClose: () => void,
  ctx: { sessionEquity: number | null; savedDsl: string | null; savedVersion: number }
): { inline: ReactNode; rail: ReactNode } | null {
  const { tree, updateBlock, setWeightAllocation, addAsset } = useStrategyBuilderStoreWithContext();
  const block = blockId ? tree.blocks[blockId] : undefined;
  const weight: WeightBlock | null = block?.type === 'weight' ? block : null;
  const [locked, setLocked] = useState<ReadonlySet<BlockId>>(new Set());
  const [live, setLive] = useState<number[] | null>(null);
  useEffect(() => {
    setLocked(new Set());
    setLive(null);
  }, [blockId]);

  const rows = useMemo(
    () => (weight ? weight.childIds.map((id) => rowOf(tree.blocks[id], id)) : []),
    [weight, tree]
  );

  const savedWeight = useMemo(() => {
    if (!ctx.savedDsl || !weight) return null;
    const saved = fromDSLString(ctx.savedDsl);
    if (!saved) return null;
    const beforeId = matchBlocks(saved.tree, tree).get(weight.id);
    const before = beforeId ? saved.tree.blocks[beforeId] : undefined;
    if (before?.type !== 'weight') return null;
    return {
      block: before,
      rows: before.childIds.map((id) => rowOf(saved.tree.blocks[id], id)),
    };
  }, [ctx.savedDsl, weight, tree]);

  const writeAll = useCallback(
    (next: readonly number[]) => {
      if (!weight) return;
      weight.childIds.forEach((id, i) => {
        if ((weight.allocations[id] ?? 0) !== next[i]) setWeightAllocation(weight.id, id, next[i]);
      });
    },
    [weight, setWeightAllocation]
  );

  if (!weight) return null;

  const stored = knownWeights(weight);
  const weights = live ?? stored;
  const specified = weight.method === 'specified';
  const lockFlags = weight.childIds.map((id) => locked.has(id));
  const lockedNames = rows.filter((r) => locked.has(r.id)).map((r) => r.label);
  const freeNames = rows.filter((r) => !locked.has(r.id)).map((r) => r.label);

  const chooseMethod = (method: WeightMethod) => {
    if (method === weight.method || method === 'market_cap') return;
    if (method === 'specified') {
      const even = splitEvenly(weight.childIds.length);
      const allocations: Record<BlockId, number> = {};
      weight.childIds.forEach((id, i) => {
        allocations[id] = weight.allocations[id] ?? even[i];
      });
      const sum = total(Object.values(allocations));
      updateBlock(weight.id, {
        method,
        allocations:
          Math.abs(sum - 100) < 0.05
            ? allocations
            : Object.fromEntries(weight.childIds.map((id, i) => [id, even[i]])),
      });
      return;
    }
    updateBlock(weight.id, {
      method,
      lookbackDays: methodUsesLookback(method) ? (weight.lookbackDays ?? 60) : undefined,
      top: method === 'momentum' ? weight.top : undefined,
    });
  };

  const inline = (
    <section
      aria-label="Edit how this block splits its share"
      className="mb-3 mt-1 overflow-hidden rounded-panel border border-accent/50 bg-panel shadow-[0_0_0_3px_var(--accent-soft)]"
      onClick={(e) => e.stopPropagation()}
    >
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h4 className="m-0 text-[13px] font-semibold text-fg">Method</h4>
        <span className="flex items-center gap-2 text-[12px] text-fg-3">
          how this block splits its share
          <button
            type="button"
            onClick={onClose}
            aria-label="Close the weights"
            className="grid h-7 w-7 place-items-center rounded-[6px] text-fg-3 hover:bg-sunk hover:text-fg"
          >
            <X className="h-4 w-4" />
          </button>
        </span>
      </header>
      <div className="grid gap-2 border-b border-line px-4 py-4">
        <div
          role="radiogroup"
          aria-label="Weight method"
          className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7"
        >
          {METHODS.map((m) => {
            const on = weight.method === m.method;
            const off = m.method === 'market_cap';
            return (
              <button
                key={m.method}
                type="button"
                role="radio"
                aria-checked={on}
                aria-disabled={off}
                disabled={off && !on}
                onClick={() => chooseMethod(m.method)}
                className={`grid content-start gap-1 rounded-[6px] border px-2.5 py-2 text-left ${
                  on
                    ? 'border-accent bg-accent-soft'
                    : off
                      ? 'cursor-not-allowed border-line text-fg-3 opacity-60'
                      : 'border-line hover:border-line-strong'
                }`}
              >
                <span className="break-words font-mono text-[12px] text-fg">{m.code}</span>
                <span className="text-[11.5px] text-fg-3">{m.hint}</span>
              </button>
            );
          })}
        </div>
        <p className="m-0 text-[12px] text-fg-3">
          market-cap needs company fundamentals the engine doesn’t have, so the check rejects it.
        </p>
      </div>

      <div className="grid gap-3 px-4 py-4">
        {specified && weights && rows.length > 0 && (
          <>
            {rows.length > 1 ? (
              <WeightBar
                rows={rows}
                weights={weights}
                onLive={setLive}
                onCommit={(w) => writeAll(w)}
              />
            ) : null}
            <div className="flex justify-between text-[12px] text-fg-3">
              <span>Dragging moves weight between the two neighbours only.</span>
              <span
                className={`font-mono ${Math.abs(total(weights) - 100) > 0.05 ? 'text-risk' : ''}`}
              >
                Total {total(weights)}%
              </span>
            </div>
          </>
        )}

        <ul className="m-0 list-none p-0">
          {rows.map((r, i) => (
            <li
              key={r.id}
              className="grid grid-cols-[10px_56px_minmax(0,1fr)_auto] items-center gap-3 border-b border-line py-2.5 text-[13px] last:border-b-0 sm:grid-cols-[10px_64px_minmax(0,1fr)_auto_28px]"
            >
              <i
                className="inline-block h-2 w-2 rounded-[1px]"
                style={{ background: HOLDING_FILLS[i % HOLDING_FILLS.length] }}
              />
              <b className="truncate font-mono text-[12.5px] font-semibold">{r.label}</b>
              <span className="truncate text-fg-2">{r.name}</span>
              {specified && weights ? (
                <NumberCell
                  label={`${r.label} weight`}
                  value={weights[i] ?? 0}
                  suffix="%"
                  min={0}
                  max={100}
                  integer={false}
                  onCommit={(v) => writeAll(setWeight(weights, lockFlags, i, v))}
                />
              ) : (
                <span className="text-right text-[12px] text-fg-3">
                  {weight.method === 'equal' && weights
                    ? `${weights[i]}%`
                    : `By ${methodWords(weight.method)}`}
                </span>
              )}
              {specified ? (
                <button
                  type="button"
                  aria-pressed={locked.has(r.id)}
                  aria-label={locked.has(r.id) ? `Unlock ${r.label}` : `Lock ${r.label}`}
                  onClick={() =>
                    setLocked((s) => {
                      const next = new Set(s);
                      if (next.has(r.id)) next.delete(r.id);
                      else next.add(r.id);
                      return next;
                    })
                  }
                  className={`hidden h-7 w-7 place-items-center rounded-[6px] hover:bg-sunk sm:grid ${locked.has(r.id) ? 'text-fg' : 'text-fg-3'}`}
                >
                  {locked.has(r.id) ? (
                    <Lock className="h-3.5 w-3.5" />
                  ) : (
                    <Unlock className="h-3.5 w-3.5" />
                  )}
                </button>
              ) : (
                <span className="hidden sm:block" />
              )}
            </li>
          ))}
        </ul>

        {!specified && weight.method !== 'equal' && (
          <div className="flex flex-wrap items-center gap-4 text-[13px] text-fg-2">
            {methodUsesLookback(weight.method) && (
              <label className="flex items-center gap-2">
                Lookback
                <NumberCell
                  label="Lookback days"
                  value={weight.lookbackDays ?? 60}
                  suffix="days"
                  min={1}
                  max={2520}
                  integer
                  onCommit={(v) => updateBlock(weight.id, { lookbackDays: v })}
                />
              </label>
            )}
            {weight.method === 'momentum' && (
              <label className="flex items-center gap-2">
                Hold the top
                <NumberCell
                  label="How many to hold"
                  value={weight.top ?? weight.childIds.length}
                  min={1}
                  max={500}
                  integer
                  onCommit={(v) => updateBlock(weight.id, { top: v })}
                />
              </label>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <AddSymbol onAdd={(symbol) => addAsset(weight.id, symbol, '', symbol)} />
          {specified && rows.length > 1 && (
            <button
              type="button"
              onClick={() => writeAll(splitEvenly(rows.length))}
              className="btn btn-ghost btn-sm text-fg"
            >
              Split evenly
            </button>
          )}
          {specified && lockedNames.length > 0 && (
            <span className="ml-auto text-[12px] text-fg-3">
              {lockedNames.join(' and ')} {lockedNames.length === 1 ? 'is' : 'are'} locked, so
              changes move between {freeNames.join(', ') || 'no other rows'}.
            </span>
          )}
        </div>
      </div>
    </section>
  );

  const share = shareOfWhole(tree, weight.id);
  const savedKnown = savedWeight ? knownWeights(savedWeight.block) : null;
  const segments = (rs: readonly WeightRow[], ws: readonly number[]) =>
    rs.map((r, i) => ({
      key: r.id,
      pct: ws[i] ?? 0,
      fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
    }));
  const legend = (rs: readonly WeightRow[], ws: readonly number[] | null, method: WeightMethod) =>
    ws
      ? rs
          .map((r, i) => `${r.label} ${Math.round((ws[i] ?? 0) * 10) / 10}%`)
          .filter((_, i) => (ws[i] ?? 0) > 0)
          .join('  ')
      : `${rs.map((r) => r.label).join(' ')} by ${methodWords(method)}`;

  const rail = (
    <div className="grid gap-4">
      {ctx.sessionEquity !== null && (
        <RailPanel
          title="In dollars"
          meta={
            <>
              on <Money value={ctx.sessionEquity} />
            </>
          }
        >
          {weights && share !== null ? (
            <div>
              {rows.map((r, i) => (
                <KeyValue
                  key={r.id}
                  k={`${r.label} ${Math.round((weights[i] ?? 0) * 10) / 10}%`}
                  v={<Money value={((ctx.sessionEquity ?? 0) * share * (weights[i] ?? 0)) / 100} />}
                />
              ))}
            </div>
          ) : (
            <p className="m-0 text-[12.5px] text-fg-2">
              This split is decided at each rebalance, so there’s no fixed dollar figure.
            </p>
          )}
          <p className="m-0 text-[12px] leading-[1.55] text-fg-3">
            The paper session’s current equity, if this rule applied. The session keeps running its
            version until you switch it to a saved one.
          </p>
        </RailPanel>
      )}
      {savedWeight && (
        <RailPanel title={`Against version ${ctx.savedVersion}`}>
          <div className="grid gap-1.5">
            {savedKnown && (
              <StackedBar
                label={`Version ${ctx.savedVersion}`}
                height={8}
                segments={segments(savedWeight.rows, savedKnown)}
              />
            )}
            <span className="font-mono text-[11.5px] text-fg-2">
              {legend(savedWeight.rows, savedKnown, savedWeight.block.method)}{' '}
              <span className="text-fg-3">version {ctx.savedVersion}</span>
            </span>
          </div>
          <div className="grid gap-1.5">
            {weights && <StackedBar label="Draft" height={8} segments={segments(rows, weights)} />}
            <span className="font-mono text-[11.5px] text-fg-2">
              {legend(rows, weights, weight.method)} <span className="text-fg-3">draft</span>
            </span>
          </div>
        </RailPanel>
      )}
    </div>
  );

  return { inline, rail };
}
