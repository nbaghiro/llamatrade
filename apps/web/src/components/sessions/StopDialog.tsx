import { ArrowRight, Pause, X } from 'lucide-react';

import { formatMoney, formatNumber } from '../../lib/format';
import { LaneMarker } from '../charts';
import { Dialog } from '../ui/Dialog';
import { ModeBadge, type AccountMode } from '../ui/ModeBadge';

import { etDayLabel, etHm } from './timeline';

export interface StopHolding {
  symbol: string;
  quantity: number;
  value: number;
}

interface StopDialogProps {
  open: boolean;
  onClose: () => void;
  name: string;
  mode: AccountMode;
  holdings: readonly StopHolding[];
  cash: number | null;
  /** Recent rebalance days, oldest first, for the short lane. */
  recent: readonly Date[];
  /** The rebalance that won't run, e.g. "Dec 1 rebalance". */
  nextLabel: string | null;
  now: Date;
  /** Offered as the gentler choice when the session can pause. */
  onPause?: () => void;
  onStop: () => void;
}

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** Stop asks once and draws where each holding goes: shares to Unmanaged, cash to Unallocated (stop2 A). */
export function StopDialog({
  open,
  onClose,
  name,
  mode,
  holdings,
  cash,
  recent,
  nextLabel,
  now,
  onPause,
  onStop,
}: StopDialogProps) {
  const account = mode === 'live' ? 'Alpaca live account' : 'Alpaca paper account';
  const rings = recent.slice(-4);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      width={680}
      title={
        <span className="flex items-center gap-2.5">
          Stop {name}?
          <ModeBadge mode={mode} size="sm" />
        </span>
      }
      footer={
        <>
          <button type="button" className="btn btn-ghost mr-auto" onClick={onClose}>
            Cancel
          </button>
          {onPause && (
            <button type="button" className="btn btn-secondary" onClick={onPause}>
              Pause instead
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={onStop}>
            Stop {name}
          </button>
        </>
      }
    >
      <p className="m-0 text-[13px] text-fg-2">
        Stopping closes this session&apos;s sleeve. Nothing is sold.
      </p>
      <div className="grid gap-x-3 gap-y-2 sm:grid-cols-[minmax(0,1fr)_16px_minmax(0,1fr)]">
        <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
          In this sleeve now
        </div>
        <span className="hidden sm:block" />
        <div className="hidden text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3 sm:block">
          After you stop
        </div>
        <div className="grid gap-1.5">
          {holdings.length === 0 && (
            <div className="rounded-[8px] border border-line px-3 py-2.5 text-[12.5px] text-fg-3">
              No shares held
            </div>
          )}
          {holdings.map((h) => (
            <div
              key={h.symbol}
              className="flex items-center justify-between gap-3 rounded-[8px] border border-line px-3 py-2.5 text-[12.5px]"
            >
              <span>
                <b className="font-mono font-semibold">{h.symbol}</b>{' '}
                <span className="text-fg-3">{qty(h.quantity)} shares</span>
              </span>
              <span className="num">{formatMoney(h.value)}</span>
            </div>
          ))}
          {cash !== null && (
            <div className="flex items-center justify-between gap-3 rounded-[8px] border border-line px-3 py-2.5 text-[12.5px]">
              <span>Cash</span>
              <span className="num">{formatMoney(cash)}</span>
            </div>
          )}
        </div>
        <div className="hidden flex-col justify-around text-fg-3 sm:flex">
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
          {cash !== null && holdings.length > 0 && (
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          )}
        </div>
        <div className="grid gap-1.5">
          {holdings.length > 0 && (
            <div className="rounded-[8px] border border-dashed border-line-strong bg-sunk px-3 py-2.5 text-[12.5px]">
              <b className="block font-semibold">Unmanaged</b>
              <span className="text-fg-2">
                Still held in your {account}. No strategy trades them, and you can sell them there
                or assign them to a new session.
              </span>
            </div>
          )}
          {cash !== null && (
            <div className="rounded-[8px] border border-dashed border-line-strong bg-sunk px-3 py-2.5 text-[12.5px]">
              <b className="block font-semibold">Unallocated</b>
              <span className="text-fg-2">
                Free cash in Alpaca {mode}, ready for another session.
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="relative h-8" aria-hidden="true">
        <i className="absolute left-0 top-1/2 w-[70%] border-t-[1.5px] border-accent/60" />
        <i className="absolute left-[70%] right-0 top-1/2 border-t-[1.5px] border-dashed border-fg-3/40" />
        {rings.length > 0 && (
          <span className="absolute -top-1 left-0 font-mono text-[10.5px] text-fg-3">
            {etDayLabel(rings[0])}
          </span>
        )}
        {rings.map((d, i) => (
          <LaneMarker
            key={d.getTime()}
            shape="ring"
            positioned
            style={{ left: `${8 + (i * 58) / Math.max(1, rings.length)}%` }}
          />
        ))}
        <LaneMarker shape="stop" positioned style={{ left: '70%' }} />
        <span className="absolute -top-2.5 left-[70%] -translate-x-1/2 whitespace-nowrap rounded bg-fg px-1.5 py-px font-mono text-[10px] font-semibold text-canvas">
          Stop {etHm(now)}
        </span>
        {nextLabel && (
          <span className="absolute left-[76%] top-1/2 flex -translate-y-1/2 items-center gap-1 bg-panel pr-1 font-mono text-[11px] text-fg-3 line-through">
            <X className="h-3.5 w-3.5 text-fg-2" aria-hidden="true" />
            {nextLabel}
          </span>
        )}
      </div>

      <p className="m-0 text-[12.5px] text-fg-2">
        {nextLabel ? `The ${nextLabel} won't run, and no` : 'No'} orders are placed for this session
        from now on. A stop can&apos;t be undone. To run {name} again you start a new session, which
        gets a new sleeve.
        {mode === 'live' &&
          ' The holdings stay in your live account as real positions until you sell them.'}
      </p>
      {onPause && (
        <div className="flex gap-2.5 rounded-[8px] border border-line bg-sunk px-3 py-2.5 text-[12.5px]">
          <Pause className="mt-0.5 h-3.5 w-3.5 flex-none text-fg-3" aria-hidden="true" />
          <span className="text-fg-2">
            <b className="font-semibold text-fg">Pause keeps everything as it is.</b> The sleeve and
            its holdings stay, and rebalances are skipped until you resume.
          </span>
        </div>
      )}
    </Dialog>
  );
}
