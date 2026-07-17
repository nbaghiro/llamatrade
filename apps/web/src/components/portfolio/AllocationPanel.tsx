/**
 * Capital allocation donut: deployed strategy sleeves plus free cash, as a
 * share of total book.
 */

import type { StrategyPerformance } from '@llamatrade/core/stores/portfolio';

interface AllocationPanelProps {
  strategies: StrategyPerformance[];
  freeCash: number;
  totalBook: number;
}

const FREE_CASH_COLOR = '#7a7362'; // Monolith warm-neutral

const RADIUS = 60;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function currency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function abbreviate(value: number): string {
  if (Math.abs(value) >= 1000) return `$${Math.round(value / 1000)}K`;
  return currency(value);
}

export default function AllocationPanel({ strategies, totalBook }: AllocationPanelProps) {
  // One basis = live market value: strategy slices + a single "Free Cash" slice, so the donut closes to 100% of equity.
  const strategySlices = strategies
    .filter((s) => s.currentValue > 0)
    .map((s) => ({ label: s.name, value: s.currentValue, color: s.color }));
  const deployed = strategySlices.reduce((sum, s) => sum + s.value, 0);
  const idleCash = Math.max(0, totalBook - deployed);
  const slices = [
    ...strategySlices,
    ...(idleCash > 0 ? [{ label: 'Free Cash', value: idleCash, color: FREE_CASH_COLOR }] : []),
  ];
  const denominator = totalBook > 0 ? totalBook : slices.reduce((sum, s) => sum + s.value, 0);

  let cumulative = 0;
  const arcs = slices.map((slice) => {
    const fraction = denominator > 0 ? slice.value / denominator : 0;
    const length = fraction * CIRCUMFERENCE;
    const arc = {
      ...slice,
      fraction,
      dasharray: `${length} ${CIRCUMFERENCE - length}`,
      dashoffset: -cumulative,
    };
    cumulative += length;
    return arc;
  });

  return (
    <div className="bg-paper border-2 border-ink shadow">
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b-2 border-ink gap-3">
        <span className="font-mono text-[11.5px] font-bold uppercase tracking-[0.1em] text-ink">Allocation</span>
        <div className="flex gap-1.5">
          <span className="font-mono text-[10px] font-bold uppercase tracking-wide border-[1.5px] border-ink px-2 py-1 bg-ink text-bone">
            By Strategy
          </span>
          <span className="font-mono text-[10px] font-bold uppercase tracking-wide border-[1.5px] border-ink px-2 py-1 text-ink/40">
            By Asset
          </span>
        </div>
      </div>

      <div className="flex items-center gap-5 px-[18px] py-5 flex-wrap">
        <svg width="170" height="170" viewBox="0 0 170 170" className="flex-none">
          <g transform="rotate(-90 85 85)">
            {arcs.map((arc, i) => (
              <circle
                key={i}
                cx="85"
                cy="85"
                r={RADIUS}
                fill="none"
                stroke={arc.color}
                strokeWidth="26"
                strokeDasharray={arc.dasharray}
                strokeDashoffset={arc.dashoffset}
              />
            ))}
          </g>
          <circle cx="85" cy="85" r="47" className="fill-paper" />
          <text
            x="85"
            y="80"
            textAnchor="middle"
            className="fill-ink"
            fontFamily="Space Mono"
            fontWeight="700"
            fontSize="21"
          >
            {abbreviate(totalBook)}
          </text>
          <text
            x="85"
            y="98"
            textAnchor="middle"
            fill="rgba(13,13,13,.5)"
            fontFamily="Space Mono"
            fontWeight="700"
            fontSize="9"
            letterSpacing="1"
          >
            TOTAL BOOK
          </text>
        </svg>

        <div className="flex-1 min-w-[180px] flex flex-col gap-2.5">
          {arcs.length === 0 ? (
            <span className="font-mono text-xs text-ink/40 italic">No capital allocated</span>
          ) : (
            arcs.map((arc, i) => (
              <div key={i} className="flex items-center gap-2.5 text-[12.5px]">
                <span className="w-3 h-3 flex-none border-2 border-ink" style={{ backgroundColor: arc.color }} />
                <span className="font-semibold text-ink">{arc.label}</span>
                <span className="ml-auto font-mono text-[10px] text-ink/45 tabular-nums min-w-[64px] text-right">
                  {currency(arc.value)}
                </span>
                <span className="font-mono font-bold text-[13px] tabular-nums w-10 text-right">
                  {(arc.fraction * 100).toFixed(0)}%
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
