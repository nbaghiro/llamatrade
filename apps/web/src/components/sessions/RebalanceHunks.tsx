import { OrderSide } from '@llamatrade/core/proto/trading_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { ArrowRightLeft, Briefcase, Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney } from '../../lib/format';

import {
  lineNote,
  netText,
  sharesText,
  tradeText,
  weightText,
  type HoldingLine,
  type RebalanceDiff,
} from './rebalanceDiff';

export type DiffView = 'split' | 'unified';

const ROW = 'grid gap-2.5 px-3.5 font-mono text-[12.5px] leading-[30px] whitespace-nowrap';
const UNIFIED_COLS = 'grid-cols-[18px_56px_minmax(0,1fr)_96px]';
const SPLIT_COLS = 'grid-cols-[18px_48px_minmax(0,1fr)_56px]';

type Side = 'del' | 'add' | 'same';

function sideClass(side: Side) {
  if (side === 'del') return 'bg-sunk text-fg-3';
  if (side === 'add') return 'bg-accent-soft';
  return '';
}

function Sign({ side }: { side: Side }) {
  if (side === 'same') return <span aria-hidden="true" />;
  return (
    <span
      aria-hidden="true"
      className={`text-center ${side === 'add' ? 'font-semibold text-accent' : 'text-fg-3'}`}
    >
      {side === 'add' ? '+' : '−'}
    </span>
  );
}

function money(v: number | null) {
  return v === null ? 'price not recorded' : formatMoney(v);
}

function weight(v: number | null) {
  return v === null ? '·' : weightText(v);
}

function sideText(line: HoldingLine, at: 'before' | 'after') {
  const q = at === 'before' ? line.before : line.after;
  const v = at === 'before' ? line.valueBefore : line.valueAfter;
  return `${sharesText(q)} ${q === 1 ? 'share' : 'shares'}   ${money(v)}`;
}

function Strike({ on, children }: { on: boolean; children: ReactNode }) {
  return (
    <span
      className={`overflow-hidden text-ellipsis whitespace-pre ${on ? 'line-through decoration-fg-3' : ''}`}
    >
      {children}
    </span>
  );
}

function UnifiedLine({ line, side }: { line: HoldingLine; side: Side }) {
  const at = side === 'del' ? 'before' : 'after';
  const trade = side === 'add' ? tradeText(line) : '';
  return (
    <div className={`${ROW} ${UNIFIED_COLS} ${sideClass(side)}`}>
      <Sign side={side} />
      <Strike on={side === 'del'}>{line.symbol}</Strike>
      <Strike on={side === 'del'}>
        {sideText(line, at)}
        {trade && <span className="text-fg-2">{`   ${trade}`}</span>}
      </Strike>
      <span className={`text-right ${side === 'add' ? 'text-fg-2' : 'text-fg-3'}`}>
        {weight(at === 'before' ? line.weightBefore : line.weightAfter)}
      </span>
    </div>
  );
}

function SplitCell({ line, side }: { line: HoldingLine; side: Side }) {
  const at = side === 'del' ? 'before' : 'after';
  const empty = (side === 'del' && line.before === 0) || (side === 'add' && line.after === 0);
  return (
    <div className={`${ROW} ${SPLIT_COLS} ${empty ? '' : sideClass(side)}`}>
      <Sign side={empty ? 'same' : side} />
      <Strike on={side === 'del'}>{line.symbol}</Strike>
      <Strike on={side === 'del'}>{empty ? 'none' : sideText(line, at)}</Strike>
      <span className="text-right text-fg-3">
        {weight(at === 'before' ? line.weightBefore : line.weightAfter)}
      </span>
    </div>
  );
}

function Note({ children }: { children: ReactNode }) {
  return (
    <div className="mx-3.5 my-2 grid grid-cols-[24px_minmax(0,1fr)] gap-2.5 rounded-[8px] border border-line bg-panel px-3 py-2.5 text-[12.5px] leading-normal text-fg-2 md:ml-[46px]">
      <span className="grid h-6 w-6 place-items-center rounded-full bg-sunk">
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <div>{children}</div>
    </div>
  );
}

function HunkHead({ icon, title, aside }: { icon: ReactNode; title: string; aside?: string }) {
  return (
    <div className="flex items-center gap-2.5 border-b border-line bg-sunk px-3.5 py-2 font-mono text-[12px] font-medium text-fg-2">
      {icon}
      <span>{title}</span>
      {aside && <span className="ml-auto truncate font-normal text-fg-3">{aside}</span>}
    </div>
  );
}

function HoldingsHunk({ diff, view }: { diff: RebalanceDiff; view: DiffView }) {
  const traded = diff.lines.filter((l) => l.changed && l.bought + l.sold > 0);
  const cashNote =
    traded.length > 0
      ? `The sells paid in ${formatMoney(diff.cashIn)} and the buys spent ${formatMoney(diff.cashOut)}. The sleeve's cash before and after isn't recorded yet, so cash isn't in this diff or in the weights.`
      : "The sleeve's cash before and after isn't recorded yet, so cash isn't in this diff or in the weights.";
  return (
    <section id="holdings" className="overflow-hidden rounded-[10px] border border-line bg-panel">
      <HunkHead
        icon={<Briefcase className="h-3.5 w-3.5" aria-hidden="true" />}
        title="holdings"
        aside="shares · value at fill prices · weight of holdings"
      />
      <div className="overflow-x-auto">
        {diff.lines.map((line) => {
          const note = lineNote(line);
          if (!line.changed) {
            return view === 'split' ? (
              <div key={line.symbol} className="grid grid-cols-2 divide-x divide-line">
                <SplitCell line={line} side="same" />
                <SplitCell line={line} side="same" />
              </div>
            ) : (
              <UnifiedLine key={line.symbol} line={line} side="same" />
            );
          }
          return (
            <div key={line.symbol}>
              {view === 'split' ? (
                <>
                  <div className="grid grid-cols-2 divide-x divide-line">
                    <SplitCell line={line} side="del" />
                    <SplitCell line={line} side="add" />
                  </div>
                  <div className="px-3.5 pb-1 text-right font-mono text-[11.5px] text-fg-3">
                    {tradeText(line)}
                  </div>
                </>
              ) : (
                <>
                  {line.before !== 0 && <UnifiedLine line={line} side="del" />}
                  {line.after !== 0 && <UnifiedLine line={line} side="add" />}
                  {line.after === 0 && (
                    <div className={`${ROW} ${UNIFIED_COLS} bg-accent-soft`}>
                      <Sign side="add" />
                      <span>{line.symbol}</span>
                      <span className="overflow-hidden text-ellipsis whitespace-pre">
                        none<span className="text-fg-2">{`   ${tradeText(line)}`}</span>
                      </span>
                      <span className="text-right text-fg-2">{weight(line.weightAfter)}</span>
                    </div>
                  )}
                </>
              )}
              {note && <Note>{note}</Note>}
            </div>
          );
        })}
      </div>
      <p className="m-0 border-t border-line px-3.5 py-2.5 text-[12px] text-fg-3">{cashNote}</p>
    </section>
  );
}

function OrdersHunk({ diff }: { diff: RebalanceDiff }) {
  return (
    <section id="orders" className="overflow-hidden rounded-[10px] border border-line bg-panel">
      <HunkHead
        icon={<ArrowRightLeft className="h-3.5 w-3.5" aria-hidden="true" />}
        title="orders"
        aside={`${diff.ordersFilled} filled`}
      />
      <ol className="m-0 list-none p-0">
        {diff.orders.map((o) => {
          const q = toNumber(o.filledQuantity) || 0;
          const p = toNumber(o.averageFillPrice);
          return (
            <li key={o.id} className="border-b border-line last:border-b-0">
              <Link
                to={`/trading/orders/${o.id}`}
                className="flex items-center gap-3 px-3.5 py-2 font-mono text-[12.5px] hover:bg-sunk"
              >
                <span className="w-9 text-[10.5px] font-semibold text-fg-2">
                  {o.side === OrderSide.SELL ? 'SELL' : 'BUY'}
                </span>
                <span className="min-w-0 flex-1 truncate">
                  {sharesText(q)} {o.symbol}
                  {p > 0 ? ` at ${formatMoney(p)}` : ''}
                </span>
                <span className="text-fg-2">{p > 0 ? formatMoney(q * p) : '·'}</span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** The opened rebalance as a change set: holdings, then the orders behind it (rebalance2 D). */
export function RebalanceHunks({ diff, view }: { diff: RebalanceDiff; view: DiffView }) {
  return (
    <div className="flex min-w-0 flex-col gap-3.5">
      <HoldingsHunk diff={diff} view={view} />
      <OrdersHunk diff={diff} />
    </div>
  );
}

/** The phone's unified diff: one card per hunk, short lines. */
export function RebalanceHunksCompact({ diff }: { diff: RebalanceDiff }) {
  const line = (side: Side, text: string, key: string) => (
    <div
      key={key}
      className={`whitespace-pre px-3 font-mono text-[12px] leading-[1.9] ${sideClass(side)}`}
    >
      {text}
    </div>
  );
  return (
    <div className="flex flex-col gap-3">
      <section className="overflow-hidden rounded-[10px] border border-line bg-panel">
        <HunkHead icon={null} title="holdings" />
        {diff.lines.flatMap((l) => {
          const sym = l.symbol.padEnd(5);
          if (!l.changed)
            return [
              line(
                'same',
                `  ${sym}${sharesText(l.after).padStart(5)}   ${weight(l.weightAfter)}`,
                l.symbol
              ),
            ];
          return [
            ...(l.before !== 0
              ? [
                  line(
                    'del',
                    `− ${sym}${sharesText(l.before).padStart(5)}   ${weight(l.weightBefore)}`,
                    `${l.symbol}-`
                  ),
                ]
              : []),
            line(
              'add',
              `+ ${sym}${sharesText(l.after).padStart(5)}   ${weight(l.weightAfter)}   ${netText(l)}`,
              `${l.symbol}+`
            ),
          ];
        })}
      </section>
      <OrdersHunk diff={diff} />
      <p className="m-0 text-[12px] text-fg-3">
        Cash before and after, which rule ran and the inputs it read aren&apos;t recorded yet.
      </p>
    </div>
  );
}
