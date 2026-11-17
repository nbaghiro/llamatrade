import type { BacktestMetrics, BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';
import { X } from 'lucide-react';
import { Link } from 'react-router-dom';

import { alignTo, longDate } from '../../../lib/backtestView';
import { formatMoney, formatPct } from '../../../lib/format';
import { toCurve } from '../../backtest/runData';
import { AnnotatedCurve } from '../../charts';
import { PanelError, SkeletonChart } from '../../ui';

import type { HandoffState } from './useHandoffRun';

interface HandoffPanelProps {
  state: HandoffState;
  version: number;
  onRetry: () => void;
  onClose: () => void;
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-[4px] bg-sunk px-1.5 py-[3px] font-mono text-[11.5px] text-fg-2">
      {children}
    </span>
  );
}

function settingsChips(run: BacktestRun): string[] {
  const c = run.config;
  if (!c) return [];
  const start = toDate(c.startDate);
  const end = toDate(c.endDate);
  const out: string[] = [];
  if (start && end) out.push(`${longDate(start)} to ${longDate(end)}`);
  out.push(formatMoney(toNumber(c.initialCapital), { dp: 0 }));
  if (c.benchmarkSymbol) out.push(c.benchmarkSymbol);
  if (c.timeframe) out.push(c.timeframe);
  out.push(`${formatMoney(toNumber(c.commission))} commission`);
  return out;
}

type Row = [string, (m: BacktestMetrics) => number, 'pct' | 'num'];
const ROWS: Row[] = [
  ['Return', (m) => toNumber(m.totalReturn), 'pct'],
  ['Max drawdown', (m) => -Math.abs(toNumber(m.maxDrawdown)), 'pct'],
  ['Sharpe', (m) => toNumber(m.sharpeRatio), 'num'],
];

function fmt(v: number, kind: 'pct' | 'num'): string {
  return kind === 'pct' ? formatPct(v, { dp: 1, signed: true }) : v.toFixed(2);
}

function changeText(d: number, kind: 'pct' | 'num'): string {
  if (kind === 'num') return `${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(2)}`;
  const pts = Math.round(d * 1000) / 10;
  return `${pts >= 0 ? '+' : '−'}${Math.abs(pts).toFixed(1)} pts`;
}

/** handoff2 A: the new version's backtest beside the editor, against the run it copied. */
export function HandoffPanel({ state, version, onRetry, onClose }: HandoffPanelProps) {
  const { run, base, phase } = state;
  const baseVersion = base?.strategyVersion;
  const title = baseVersion
    ? `Version ${version} against version ${baseVersion}`
    : `Backtest of version ${version}`;

  let body: React.ReactNode;
  if (phase === 'failed') {
    body = (
      <PanelError
        title="The backtest didn’t finish"
        cause={state.error ?? undefined}
        unaffected={`Version ${version} is saved either way.`}
        onRetry={onRetry}
      />
    );
  } else if (phase === 'running' || !run?.results) {
    body = (
      <div className="grid gap-3">
        <p role="status" className="m-0 text-[12.5px] text-fg-2">
          {run?.progressPercent
            ? `Running, ${run.progressPercent}%${run.currentDate ? `, at ${run.currentDate}` : ''}`
            : 'Starting the backtest'}
        </p>
        <SkeletonChart />
      </div>
    );
  } else {
    const curve = toCurve(run.results.equityCurve);
    const baseCurve = base?.results ? toCurve(base.results.equityCurve) : null;
    const aligned = baseCurve ? alignTo(curve.dates, baseCurve) : [];
    const firstBase = aligned.find((v): v is number => v !== null);
    const baseline =
      firstBase !== undefined && curve.values.length
        ? aligned.map((v) => ((v ?? firstBase) / firstBase) * curve.values[0])
        : undefined;
    const m = run.results.metrics;
    const bm = base?.results?.metrics;
    body = (
      <div className="grid gap-4">
        {curve.dates.length > 1 && (
          <AnnotatedCurve
            label={title}
            dates={curve.dates}
            values={curve.values}
            benchmark={baseline}
            height={170}
            labelWidth={0}
          />
        )}
        <div className="flex items-center gap-4 text-[11.5px] text-fg-2">
          <span className="flex items-center gap-1.5">
            <i className="inline-block h-[2px] w-4 bg-accent" aria-hidden="true" />
            Version {version}
          </span>
          {baseline && (
            <span className="flex items-center gap-1.5">
              <i
                className="inline-block h-0 w-4 border-t border-dashed border-fg-3"
                aria-hidden="true"
              />
              Version {baseVersion}
            </span>
          )}
        </div>
        {m && (
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="text-[11px] text-fg-3">
                <th className="py-1.5 text-left font-medium">Backtest</th>
                {bm && <th className="py-1.5 text-right font-medium">v{baseVersion}</th>}
                <th className="py-1.5 text-right font-medium">v{version}</th>
                {bm && <th className="py-1.5 text-right font-medium">Change</th>}
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([label, pick, kind]) => {
                const now = pick(m);
                const was = bm ? pick(bm) : null;
                const d = was === null ? null : now - was;
                return (
                  <tr key={label} className="border-t border-line">
                    <td className="py-2 text-fg-2">{label}</td>
                    {was !== null && <td className="num py-2 text-right">{fmt(was, kind)}</td>}
                    <td className="num py-2 text-right text-fg">{fmt(now, kind)}</td>
                    {d !== null && (
                      <td
                        className={`num py-2 text-right ${d > 0 ? 'text-gain' : d < 0 ? 'text-loss' : 'text-fg-3'}`}
                      >
                        {changeText(d, kind)}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <Link to={`/backtest/${run.id}`} className="justify-self-start text-[12.5px] text-accent">
          Open the full result
        </Link>
      </div>
    );
  }

  const shown = run ?? base;
  const baseDate = base ? toDate(base.completedAt ?? base.createdAt) : null;
  return (
    <section aria-label={title} className="panel panel-rim">
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <h3 className="m-0 text-[13.5px] font-semibold text-fg">{title}</h3>
        <span className="flex items-center gap-2">
          <span className="rounded-[4px] border border-dashed border-line-strong px-1.5 py-px font-mono text-[11px] text-fg-3">
            Backtest
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close the backtest"
            className="grid h-6 w-6 place-items-center rounded-[5px] text-fg-3 hover:bg-sunk hover:text-fg"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </span>
      </header>
      <div className="grid gap-3 px-5 py-4">
        {shown && (
          <div className="grid gap-1.5">
            <div className="flex flex-wrap gap-1">
              {settingsChips(shown).map((c) => (
                <Chip key={c}>{c}</Chip>
              ))}
            </div>
            <p className="m-0 text-[12px] text-fg-3">
              {base && baseDate
                ? `Same settings as version ${baseVersion}’s run on ${longDate(baseDate)}, so only the rules differ.`
                : 'No earlier run to copy, so this uses two years to today with $10,000.'}
            </p>
          </div>
        )}
        {body}
      </div>
    </section>
  );
}
