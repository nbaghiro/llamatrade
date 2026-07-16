/**
 * Metrics KPI row.
 * Six headline figures: CAGR (hero), Sharpe, Sortino, Max Drawdown,
 * Volatility, Win Rate.
 */

import type { BacktestMetrics } from '../../generated/proto/backtest_pb';
import { toNumber } from '../../store/backtest';

interface MetricsPanelProps {
  metrics: BacktestMetrics;
}

function signedPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function MetricsPanel({ metrics }: MetricsPanelProps) {
  const cagr = toNumber(metrics.annualizedReturn);
  const benchmarkReturn = toNumber(metrics.benchmarkReturn);
  const maxDrawdown = toNumber(metrics.maxDrawdown);
  const ddDuration = Math.round(toNumber(metrics.maxDrawdownDurationDays));
  const benchmark = metrics.benchmarkSymbol;

  const card = 'bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d] px-3.5 pt-3.5 pb-3';
  const lab = 'font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-ink/50';
  const val = 'font-mono font-bold text-[26px] mt-2 tabular-nums tracking-tight';
  const meta = 'font-mono text-[10px] mt-1 font-bold text-ink/50';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {/* CAGR — hero ink tile with orange offset shadow */}
      <div className="bg-ink text-bone border-2 border-ink shadow-[4px_4px_0_#ff4d1c] px-3.5 pt-3.5 pb-3">
        <div className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-bone/55">CAGR</div>
        <div className={val}>{signedPercent(cagr)}</div>
        <div className="font-mono text-[10px] mt-1 font-bold text-bone/60">
          {benchmark ? `vs ${benchmark} ${signedPercent(benchmarkReturn)}` : 'annualized'}
        </div>
      </div>

      <div className={card}>
        <div className={lab}>Sharpe</div>
        <div className={`${val} text-ink`}>{toNumber(metrics.sharpeRatio).toFixed(2)}</div>
        <div className={meta}>risk-adj</div>
      </div>

      <div className={card}>
        <div className={lab}>Sortino</div>
        <div className={`${val} text-ink`}>{toNumber(metrics.sortinoRatio).toFixed(2)}</div>
        <div className={meta}>downside</div>
      </div>

      <div className={card}>
        <div className={lab}>Max Drawdown</div>
        <div className={`${val} text-red-600`}>{signedPercent(maxDrawdown)}</div>
        <div className={meta}>{ddDuration > 0 ? `${ddDuration} days` : 'peak-to-trough'}</div>
      </div>

      <div className={card}>
        <div className={lab}>Volatility</div>
        <div className={`${val} text-ink`}>{percent(toNumber(metrics.volatility))}</div>
        <div className={meta}>annualized</div>
      </div>

      <div className={card}>
        <div className={lab}>Win Rate</div>
        <div className={`${val} text-ink`}>{percent(toNumber(metrics.winRate))}</div>
        <div className={meta}>{metrics.totalTrades} trades</div>
      </div>
    </div>
  );
}
