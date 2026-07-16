import { useNavigate } from 'react-router-dom';

import {
  ExecutionStatus,
  useDashboardStore,
  type DashboardPeriod,
  type DashboardStrategy,
} from '../../store/dashboard';

import { boundsOf, buildPath } from './chart';
import { colorForSign, fmtCurrency, fmtSignedFraction } from './format';

const SPARK_W = 90;
const SPARK_H = 26;

function statusLabel(status: ExecutionStatus): string {
  switch (status) {
    case ExecutionStatus.RUNNING:
      return 'Live';
    case ExecutionStatus.PAUSED:
      return 'Paused';
    case ExecutionStatus.ERROR:
      return 'Error';
    case ExecutionStatus.PENDING:
      return 'Pending';
    default:
      return 'Stopped';
  }
}

// Sign-aware sparkline (green up / red down) with a soft area fill — matches the
// equity hero and the strategy-detail chart. Row swatch carries the strategy color.
function Sparkline({ strategy, color }: { strategy: DashboardStrategy; color: string }) {
  const values = strategy.curve.map((p) => p.value);
  const { min, max } = boundsOf(values);
  const { line, area } = buildPath(values, SPARK_W, SPARK_H, min, max);
  if (!line) return <div style={{ width: SPARK_W, height: SPARK_H }} />;
  return (
    <svg width={SPARK_W} height={SPARK_H} viewBox={`0 0 ${SPARK_W} ${SPARK_H}`} aria-hidden="true">
      <path d={area} fill={color} fillOpacity={0.12} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  );
}

function Row({ strategy, period }: { strategy: DashboardStrategy; period: DashboardPeriod }) {
  const ret = strategy.returns[period];
  const meta = [
    strategy.descriptor,
    `${fmtCurrency(strategy.allocatedCapital)} allocated`,
    `${strategy.positionsCount} pos`,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="flex items-center gap-3.5 px-4 py-3 border-b border-line last:border-b-0">
      <span
        className="w-2.5 h-2.5 shrink-0 border-2 border-ink"
        style={{ background: strategy.color }}
      />
      <div className="flex-1 min-w-0">
        <div className="font-bold text-sm truncate">{strategy.name}</div>
        <div className="font-mono text-[10.5px] text-ink/50 uppercase tracking-[0.04em] mt-0.5 truncate">
          {meta}
        </div>
      </div>
      <Sparkline strategy={strategy} color={colorForSign(ret)} />
      <div
        className="font-mono font-bold text-[15px] text-right min-w-[64px] tabular-nums"
        style={{ color: colorForSign(ret) }}
      >
        {fmtSignedFraction(ret)}
      </div>
      {strategy.isLive ? (
        // Paper account: a running strategy trades on paper, not live capital.
        <span className="font-mono text-[9px] font-bold uppercase tracking-[0.05em] border-[1.5px] border-ink px-1.5 py-0.5 bg-orange-500 text-ink">
          Paper
        </span>
      ) : (
        <span className="font-mono text-[9px] font-bold uppercase tracking-[0.05em] border-[1.5px] border-ink px-1.5 py-0.5 text-ink/70">
          {statusLabel(strategy.status)}
        </span>
      )}
    </div>
  );
}

export default function ActiveStrategies() {
  const navigate = useNavigate();
  const strategies = useDashboardStore((s) => s.strategies);
  const selectedPeriod = useDashboardStore((s) => s.selectedPeriod);

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">
          Active Strategies
        </span>
        <button
          onClick={() => navigate('/strategies')}
          className="font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-orange-500 hover:underline"
        >
          All strategies →
        </button>
      </div>
      {strategies.length > 0 ? (
        <div>
          {strategies.map((s) => (
            <Row key={s.id} strategy={s} period={selectedPeriod} />
          ))}
        </div>
      ) : (
        <div className="px-4 py-10 text-center font-mono text-[11px] uppercase tracking-[0.08em] text-ink/40">
          No deployed strategies yet
        </div>
      )}
    </div>
  );
}
