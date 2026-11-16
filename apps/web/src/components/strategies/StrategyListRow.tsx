import { num } from '@llamatrade/core/format';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Sparkline } from '../charts';
import { Pct, Skeleton, StatusMark, type RunState } from '../ui';

interface StrategyListRowProps {
  strategy: Strategy;
  state: RunState;
  stateLabel?: string;
  to: string;
  selected: boolean;
}

/** One strategy in the list. Its curve loads only once the row scrolls into view. */
export function StrategyListRow({
  strategy,
  state,
  stateLabel,
  to,
  selected,
}: StrategyListRowProps) {
  const ref = useRef<HTMLAnchorElement>(null);
  const [seen, setSeen] = useState(false);
  const run = useStrategiesStore((s) => s.runs[strategy.id]);
  const fetchStrategyRun = useStrategiesStore((s) => s.fetchStrategyRun);

  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === 'undefined') {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setSeen(true);
      },
      { rootMargin: '120px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);

  useEffect(() => {
    if (seen) fetchStrategyRun(strategy.id).catch(() => undefined);
  }, [seen, strategy.id, fetchStrategyRun]);

  const curve = run?.results?.equityCurve.map((p) => num(p.equity)) ?? [];
  const total = run?.results?.metrics ? num(run.results.metrics.totalReturn) : null;

  return (
    <Link
      ref={ref}
      to={to}
      aria-current={selected ? 'true' : undefined}
      className={`grid grid-cols-[minmax(0,1fr)_64px_62px] items-center gap-3 border-t border-line px-4 py-3 transition-colors lg:px-[18px] ${
        selected ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]' : 'hover:bg-sunk/60'
      }`}
    >
      <span className="grid min-w-0 gap-[3px]">
        <b className="truncate text-[14px] font-semibold lg:text-[13px]">{strategy.name}</b>
        <StatusMark state={state} label={stateLabel} />
      </span>
      {run === undefined ? (
        <Skeleton className="h-[18px] w-full" still={!seen} />
      ) : curve.length > 1 ? (
        <Sparkline
          values={curve}
          width={64}
          height={26}
          label={`${strategy.name} latest backtest`}
        />
      ) : (
        <span className="col-span-2 text-right text-[11.5px] leading-tight text-fg-3">
          Not backtested yet
        </span>
      )}
      {run !== null && (
        <span className="text-right text-[12.5px] lg:text-[12.5px]">
          {total === null ? '' : <Pct value={total} pnl dp={1} />}
        </span>
      )}
    </Link>
  );
}
