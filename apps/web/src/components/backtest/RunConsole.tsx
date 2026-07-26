/**
 * Run Console — the "run a backtest" overlay. Morphs configure → running (streaming log)
 * → results, driven by the shared backtest store (runBacktest → streamProgress → results).
 * Opened from any strategy surface via useRunConsole instead of deep-linking to the page.
 */

import { BacktestStatus, type BacktestMetrics, type EquityPoint } from '@llamatrade/core/proto/backtest_pb';
import { StrategyStatus, type Strategy } from '@llamatrade/core/proto/strategy_pb';
import { type BacktestConfig, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { Ban, CheckCircle, ChevronDown, Loader2, Play, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useRunConsole } from '../../store/runConsole';

import EquityCurveChart from './EquityCurveChart';
import MetricsPanel from './MetricsPanel';

type Phase = 'configure' | 'running' | 'results' | 'failed';

const RANGE_PRESETS: { label: string; years: number }[] = [
  { label: '1Y', years: 1 },
  { label: '3Y', years: 3 },
  { label: '5Y', years: 5 },
  { label: 'MAX', years: 15 },
];

const BENCHMARKS = ['SPY', 'QQQ', 'IWM', 'DIA'];

// Light hairline field — recedes so the modal reads calmer than the 2px `.input`.
const FIELD =
  'w-full border border-ink/15 bg-bone px-3 py-2 font-mono text-sm text-ink transition-colors focus:border-orange-500 focus:outline-none';

const PHASE_STEPS = [
  { at: 0, label: 'Loading strategy' },
  { at: 15, label: 'Fetching market data' },
  { at: 40, label: 'Running simulation' },
  { at: 90, label: 'Calculating metrics' },
];

function shiftYears(iso: string, years: number): string {
  const d = new Date(iso);
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().split('T')[0];
}

function statusMeta(status: StrategyStatus): { label: string; cls: string } {
  if (status === StrategyStatus.ACTIVE) return { label: 'Live', cls: 'bg-green-600 text-bone' };
  if (status === StrategyStatus.PAUSED) return { label: 'Paused', cls: 'bg-yellow-400 text-ink' };
  return { label: 'Draft', cls: 'bg-bone text-ink' };
}

function Chip({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap border-[1.5px] border-ink px-1.5 py-[1px] font-mono text-[9px] font-bold uppercase tracking-wide ${className}`}
    >
      {children}
    </span>
  );
}

export function RunConsole() {
  const { open, strategyId, strategyName, closeRunConsole } = useRunConsole();
  const {
    config,
    setConfig,
    strategies,
    strategiesLoading,
    fetchStrategies,
    runBacktest,
    cancelBacktest,
    currentBacktest,
    progress,
    progressMessage,
    error,
    clearError,
  } = useBacktestStore();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>('configure');
  const [log, setLog] = useState<string[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const logEndRef = useRef<HTMLDivElement>(null);
  const lastMsgRef = useRef<string>('');

  const status = currentBacktest?.status;
  const results = status === BacktestStatus.COMPLETED ? currentBacktest?.results : undefined;

  // Title/name follows the actual selection (which the in-modal picker can change).
  const selectedName =
    strategies.find((s) => s.id === config.strategyId)?.name || strategyName || '';

  // On open: seed config (blank when opened without a strategy) and reset the console.
  useEffect(() => {
    if (!open) return;
    setConfig({ strategyId: strategyId ?? '' });
    fetchStrategies();
    clearError();
    setPhase('configure');
    setLog([]);
    lastMsgRef.current = '';
    setStartedAt(null);
    setElapsed(0);
  }, [open, strategyId, setConfig, fetchStrategies, clearError]);

  // Escape closes, but not mid-run (avoid orphaning the stream).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && phase !== 'running') closeRunConsole();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, phase, closeRunConsole]);

  // Accumulate streamed progress messages into the terminal log.
  useEffect(() => {
    if (phase !== 'running' || !progressMessage) return;
    if (progressMessage !== lastMsgRef.current) {
      lastMsgRef.current = progressMessage;
      setLog((prev) => [...prev, progressMessage]);
    }
  }, [progressMessage, phase]);

  // Drive phase transitions from the run status.
  useEffect(() => {
    if (phase !== 'running') return;
    if (status === BacktestStatus.COMPLETED) setPhase('results');
    else if (status === BacktestStatus.FAILED || status === BacktestStatus.CANCELLED)
      setPhase('failed');
  }, [status, phase]);

  // Elapsed clock while running.
  useEffect(() => {
    if (phase !== 'running' || startedAt === null) return;
    const id = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 200);
    return () => clearInterval(id);
  }, [phase, startedAt]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: 'end' });
  }, [log]);

  if (!open) return null;

  const handleRun = async () => {
    setLog([]);
    lastMsgRef.current = '';
    setStartedAt(Date.now());
    setElapsed(0);
    setPhase('running');
    const id = await runBacktest();
    if (!id) setPhase('failed');
  };

  const handleViewReport = () => {
    if (!currentBacktest) return;
    closeRunConsole();
    navigate(`/backtest?id=${currentBacktest.id}`);
  };

  const setRange = (years: number) =>
    setConfig({ startDate: shiftYears(config.endDate, years) });

  const modalWidth =
    phase === 'configure'
      ? 'max-w-[940px]'
      : phase === 'failed'
        ? 'max-w-[480px]'
        : 'max-w-[820px]';

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-ink/50"
        onClick={() => phase !== 'running' && closeRunConsole()}
        aria-hidden="true"
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Run backtest"
          className={`w-full ${modalWidth} border-2 border-ink bg-paper shadow-[6px_6px_0_#ff4d1c]`}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b-2 border-ink bg-ink px-6 py-5 text-bone">
            <div className="min-w-0">
              <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-bone/55">
                Backtest{phase === 'results' ? ' · Complete' : phase === 'running' ? ' · Running' : ''}
              </div>
              <div className="truncate font-display text-2xl uppercase leading-none tracking-tight">
                {selectedName || 'New Backtest'}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="badge badge-primary">Paper</span>
              <button
                onClick={closeRunConsole}
                aria-label="Close"
                disabled={phase === 'running'}
                className="grid h-6 w-6 place-items-center border-2 border-bone/30 text-bone transition-colors hover:border-bone disabled:opacity-30"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.6} />
              </button>
            </div>
          </div>

          {phase === 'configure' && (
            <ConfigureBody
              config={config}
              setConfig={setConfig}
              setRange={setRange}
              strategies={strategies}
              strategiesLoading={strategiesLoading}
              onRun={handleRun}
              error={error}
            />
          )}

          {phase === 'running' && (
            <RunningBody
              config={config}
              progress={progress}
              log={log}
              elapsed={elapsed}
              currentDate={currentBacktest?.currentDate ?? ''}
              logEndRef={logEndRef}
              onCancel={() => currentBacktest && cancelBacktest(currentBacktest.id)}
            />
          )}

          {phase === 'results' && results?.metrics && (
            <ResultsBody
              metrics={results.metrics}
              equityCurve={results.equityCurve}
              benchmarkCurve={results.benchmarkEquityCurve}
              benchmarkSymbol={results.benchmarkSymbol}
              strategyName={strategyName}
              elapsed={elapsed}
              onViewReport={handleViewReport}
              onRunAgain={() => setPhase('configure')}
            />
          )}

          {phase === 'failed' && (
            <FailedBody
              message={error || currentBacktest?.statusMessage || 'The backtest did not complete.'}
              onRetry={() => {
                clearError();
                setPhase('configure');
              }}
            />
          )}
        </div>
      </div>
    </>
  );
}

// ---------- Configure ----------

interface ConfigProps {
  config: BacktestConfig;
  setConfig: (c: Partial<BacktestConfig>) => void;
  setRange: (years: number) => void;
  strategies: Strategy[];
  strategiesLoading: boolean;
  onRun: () => void;
  error: string | null;
}

function ConfigureBody({
  config,
  setConfig,
  setRange,
  strategies,
  strategiesLoading,
  onRun,
  error,
}: ConfigProps) {
  const activeYears =
    RANGE_PRESETS.find((p) => shiftYears(config.endDate, p.years) === config.startDate)?.years ?? null;
  const selected = strategies.find((s) => s.id === config.strategyId) ?? null;

  return (
    <div className="grid max-h-[64vh] overflow-hidden md:grid-cols-[288px_1fr]">
      {/* Left — visual strategy picker */}
      <div className="flex min-h-0 flex-col border-b-2 border-ink md:border-b-0 md:border-r-2">
        <div className="shrink-0 border-b-2 border-ink px-4 py-3">
          <span className="label !mb-0">Choose strategy</span>
        </div>
        <div className="no-scrollbar min-h-0 flex-1 overflow-auto p-2">
          {strategiesLoading && strategies.length === 0 ? (
            <div className="p-3 font-mono text-[11px] text-ink/50">Loading strategies…</div>
          ) : strategies.length === 0 ? (
            <div className="p-3 font-mono text-[11px] text-ink/50">No strategies yet.</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {strategies.map((s) => {
                const active = s.id === config.strategyId;
                const meta = statusMeta(s.status);
                return (
                  <button
                    key={s.id}
                    onClick={() => setConfig({ strategyId: s.id })}
                    className={`border-2 px-3 py-2.5 text-left transition-colors ${
                      active ? 'border-orange-500 bg-orange-500/[0.06]' : 'border-ink/15 hover:border-ink'
                    }`}
                  >
                    <div className="truncate text-[13px] font-bold text-ink">{s.name}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      <Chip className={meta.cls}>{meta.label}</Chip>
                      <Chip className="text-ink/70">{(s.timeframe || '1D').toUpperCase()}</Chip>
                      <Chip className="text-ink/70">{s.symbols.length} pos</Chip>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Right — preview of the selected strategy + a clean config section */}
      <div className="no-scrollbar min-h-0 overflow-auto p-6">
        {selected ? (
          <div className="border-2 border-ink bg-bone p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="min-w-0 truncate font-display text-xl uppercase leading-none tracking-tight text-ink">
                {selected.name}
              </h3>
              <Chip className={`shrink-0 ${statusMeta(selected.status).cls}`}>
                {statusMeta(selected.status).label}
              </Chip>
            </div>
            {selected.description && (
              <p className="mt-2.5 line-clamp-2 font-mono text-[11px] leading-relaxed text-ink/60">
                {selected.description}
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-1">
              {selected.symbols.slice(0, 12).map((sym) => (
                <Chip key={sym} className="bg-paper text-blue-600">
                  {sym}
                </Chip>
              ))}
              {selected.symbols.length > 12 && (
                <Chip className="text-ink/60">+{selected.symbols.length - 12}</Chip>
              )}
              {selected.symbols.length === 0 && (
                <span className="font-mono text-[10px] uppercase tracking-wide text-ink/40">No positions</span>
              )}
            </div>
          </div>
        ) : (
          <div className="flex min-h-[116px] items-center justify-center border-2 border-dashed border-ink/25 bg-bone/60 text-center font-mono text-[11px] uppercase tracking-[0.06em] text-ink/40">
            ← Pick a strategy to preview
          </div>
        )}

        {/* Configuration */}
        <div className="mt-5 border-t-2 border-ink/10 pt-5">
          <span className="label">Date range</span>
          <div className="mb-3 grid grid-cols-4 border-2 border-ink">
            {RANGE_PRESETS.map((p, i) => (
              <button
                key={p.label}
                onClick={() => setRange(p.years)}
                className={`py-2 font-mono text-[11px] font-bold uppercase tracking-wide transition-colors ${
                  i > 0 ? 'border-l-2 border-ink' : ''
                } ${p.years === activeYears ? 'bg-ink text-bone' : 'text-ink hover:bg-ink/[0.06]'}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input
              type="date"
              aria-label="Start date"
              value={config.startDate}
              onChange={(e) => setConfig({ startDate: e.target.value })}
              className={FIELD}
            />
            <input
              type="date"
              aria-label="End date"
              value={config.endDate}
              onChange={(e) => setConfig({ endDate: e.target.value })}
              className={FIELD}
            />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div>
              <span className="label">Initial capital</span>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-ink/40">
                  $
                </span>
                <input
                  type="number"
                  aria-label="Initial capital"
                  min={0}
                  step={1000}
                  value={config.initialCapital}
                  onChange={(e) => setConfig({ initialCapital: Number(e.target.value) })}
                  className={`${FIELD} pl-7`}
                />
              </div>
            </div>
            <div>
              <span className="label">Benchmark</span>
              <div className="relative">
                <select
                  aria-label="Benchmark"
                  value={config.benchmarkSymbol}
                  onChange={(e) => setConfig({ benchmarkSymbol: e.target.value })}
                  className={`${FIELD} appearance-none pr-9`}
                >
                  <option value="">None</option>
                  {BENCHMARKS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink/50" />
              </div>
            </div>
          </div>
        </div>

        {error && (
          <p className="mt-4 border border-red-500/60 bg-red-50 px-3 py-2 font-mono text-xs text-red-700">
            {error}
          </p>
        )}

        <button
          onClick={onRun}
          disabled={!config.strategyId}
          className="btn btn-primary btn-lg mt-5 w-full"
        >
          <Play className="h-4 w-4" strokeWidth={2.6} /> Run Backtest
        </button>
      </div>
    </div>
  );
}

// ---------- Running ----------

interface RunningProps {
  config: BacktestConfig;
  progress: number;
  log: string[];
  elapsed: number;
  currentDate: string;
  logEndRef: React.RefObject<HTMLDivElement>;
  onCancel: () => void;
}

function RunningBody({ config, progress, log, elapsed, currentDate, logEndRef, onCancel }: RunningProps) {
  const pct = Math.min(100, Math.max(0, progress));
  return (
    <div className="grid grid-cols-1 md:grid-cols-[280px_1fr]">
      {/* Left: config summary + phased progress */}
      <div className="border-b-2 border-ink p-4 md:border-b-0 md:border-r-2">
        <span className="label">Configuration</span>
        <dl className="mb-4 space-y-1.5 font-mono text-[11px]">
          <div className="flex justify-between">
            <dt className="text-ink/50">Range</dt>
            <dd className="font-bold">
              {config.startDate} → {config.endDate}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink/50">Capital</dt>
            <dd className="font-bold">${config.initialCapital.toLocaleString()}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink/50">Benchmark</dt>
            <dd className="font-bold">{config.benchmarkSymbol || 'None'}</dd>
          </div>
        </dl>

        <div className="h-2.5 border-2 border-ink bg-bone">
          <div className="h-full bg-orange-500 transition-all duration-200" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[11px]">
          <span className="text-ink/60">{pct.toFixed(0)}%</span>
          <span className="text-ink/60">
            Elapsed <span className="font-bold text-ink tabular-nums">{elapsed.toFixed(1)}s</span>
          </span>
        </div>

        <ul className="mt-4 space-y-1.5">
          {PHASE_STEPS.map((step, i) => {
            const next = PHASE_STEPS[i + 1]?.at ?? 101;
            const done = pct >= next;
            const active = pct >= step.at && pct < next;
            return (
              <li key={step.label} className="flex items-center gap-2 font-mono text-[11px]">
                <span
                  className={`grid h-4 w-4 place-items-center border-2 text-[10px] font-bold ${
                    done
                      ? 'border-ink bg-green-600 text-bone'
                      : active
                        ? 'border-ink bg-orange-500 text-ink'
                        : 'border-ink/20 text-ink/30'
                  }`}
                >
                  {done ? '✓' : i + 1}
                </span>
                <span className={done || active ? 'text-ink' : 'text-ink/40'}>{step.label}</span>
              </li>
            );
          })}
        </ul>

        <button onClick={onCancel} className="btn btn-danger btn-sm mt-4 w-full">
          <Ban className="h-3.5 w-3.5" /> Cancel
        </button>
      </div>

      {/* Right: streaming terminal log */}
      <div className="min-h-[280px] bg-ink p-3 font-mono text-[11px] leading-relaxed text-bone/85">
        {log.length === 0 && (
          <div className="text-bone/40">
            <Loader2 className="mr-2 inline h-3.5 w-3.5 animate-spin" />
            starting…
          </div>
        )}
        {log.map((line, i) => (
          <div key={i} className="truncate">
            <span className="text-bone/35">›</span> {line}
          </div>
        ))}
        {currentDate && (
          <div className="text-orange-500">
            simulating <span className="text-bone">{currentDate}</span>
            <span className="ml-1 inline-block h-3 w-2 animate-pulse bg-orange-500 align-middle" />
          </div>
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

// ---------- Results ----------

interface ResultsProps {
  metrics: BacktestMetrics;
  equityCurve: EquityPoint[];
  benchmarkCurve: EquityPoint[];
  benchmarkSymbol: string;
  strategyName: string;
  elapsed: number;
  onViewReport: () => void;
  onRunAgain: () => void;
}

function ResultsBody({
  metrics,
  equityCurve,
  benchmarkCurve,
  benchmarkSymbol,
  strategyName,
  elapsed,
  onViewReport,
  onRunAgain,
}: ResultsProps) {
  return (
    <div className="p-5">
      <div className="mb-3 flex items-center gap-2 font-mono text-xs text-ink/60">
        <CheckCircle className="h-4 w-4 text-green-600" />
        Completed in <span className="font-bold text-ink">{elapsed.toFixed(1)}s</span>
      </div>

      {metrics && <MetricsPanel metrics={metrics} />}

      {equityCurve && equityCurve.length > 0 && (
        <div className="mt-4">
          <EquityCurveChart
            data={equityCurve}
            benchmark={benchmarkCurve ?? []}
            benchmarkSymbol={benchmarkSymbol}
            strategyName={strategyName}
            metrics={metrics}
          />
        </div>
      )}

      <div className="mt-5 flex gap-2.5">
        <button onClick={onViewReport} className="btn btn-primary grow">
          View full report →
        </button>
        <button onClick={onRunAgain} className="btn btn-secondary">
          Run again
        </button>
      </div>
    </div>
  );
}

// ---------- Failed ----------

function FailedBody({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="p-6">
      <div className="mb-3 flex items-center gap-2 font-display text-lg uppercase text-red-600">
        <Ban className="h-5 w-5" /> Backtest failed
      </div>
      <p className="border-2 border-ink bg-red-50 px-3 py-2 font-mono text-xs text-ink/80">{message}</p>
      <button onClick={onRetry} className="btn btn-secondary mt-4 w-full">
        Back to configure
      </button>
    </div>
  );
}
