/**
 * Configuration rail panel.
 * Strategy, date range, capital, benchmark and commission inputs plus the
 * run trigger — the left-rail control surface of the backtest workspace.
 */

import { ChevronDown, Loader2, Play } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';

import { useBacktestStore } from '@llamatrade/core/stores/backtest';

interface BacktestConfigFormProps {
  onRun: () => void;
  loading: boolean;
  lastRunLabel?: string | null;
}

const BENCHMARKS = ['SPY', 'QQQ', 'IWM', 'DIA'];
const RANGE_PRESETS: { label: string; years: number }[] = [
  { label: '1Y', years: 1 },
  { label: '3Y', years: 3 },
  { label: '5Y', years: 5 },
  { label: 'MAX', years: 15 },
];

const MS_PER_YEAR = 365.25 * 24 * 60 * 60 * 1000;

function shiftYears(from: string, years: number): string {
  const base = from ? new Date(from) : new Date();
  const d = new Date(base);
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().split('T')[0];
}

export default function BacktestConfigForm({ onRun, loading, lastRunLabel }: BacktestConfigFormProps) {
  const { config, setConfig, strategies, strategiesLoading, fetchStrategies } = useBacktestStore();

  useEffect(() => {
    fetchStrategies();
  }, [fetchStrategies]);

  const selectedStrategy = useMemo(
    () => strategies.find((s) => s.id === config.strategyId),
    [strategies, config.strategyId]
  );

  // Which quick-range chip (if any) matches the current start→end span.
  const activePreset = useMemo(() => {
    if (!config.startDate || !config.endDate) return null;
    const span = new Date(config.endDate).getTime() - new Date(config.startDate).getTime();
    const years = Math.round(span / MS_PER_YEAR);
    if (years <= 1) return '1Y';
    if (years === 3) return '3Y';
    if (years === 5) return '5Y';
    if (years >= 13) return 'MAX';
    return null;
  }, [config.startDate, config.endDate]);

  const canRun = !loading && !!config.strategyId && !!config.startDate && !!config.endDate;

  const controlBox =
    'border-2 border-ink bg-bone px-2.5 py-2.5 flex items-center justify-between text-sm font-semibold';
  const fieldLabel =
    'block font-mono text-[9.5px] font-bold uppercase tracking-[0.12em] text-ink/55 mb-1.5';

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-[15px] py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">Configuration</span>
        {selectedStrategy ? (
          <Link
            to={`/strategies/${selectedStrategy.id}`}
            className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px] bg-paper hover:bg-ink hover:text-bone transition-colors"
          >
            Edit DSL
          </Link>
        ) : (
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px] bg-paper text-ink/40">
            Edit DSL
          </span>
        )}
      </div>

      <div className="px-[15px] pt-3.5 pb-4">
        {/* Strategy */}
        <div className="mb-3">
          <label htmlFor="bt-strategy" className={fieldLabel}>Strategy</label>
          <div className="relative">
            <select
              id="bt-strategy"
              value={config.strategyId}
              onChange={(e) => setConfig({ strategyId: e.target.value })}
              disabled={strategiesLoading}
              className={`${controlBox} w-full appearance-none pr-8 outline-none focus:border-orange-500 disabled:opacity-60`}
            >
              <option value="">
                {strategiesLoading
                  ? 'Loading…'
                  : strategies.length === 0
                    ? 'No strategies'
                    : 'Select strategy'}
              </option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink/60 pointer-events-none" />
            {strategiesLoading && (
              <Loader2 className="absolute right-7 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink/50 animate-spin" />
            )}
          </div>
        </div>

        {/* DSL preview — only when the selected strategy carries source */}
        {selectedStrategy?.dslCode && (
          <pre className="border-2 border-dashed border-line bg-bone px-2.5 py-2 font-mono text-[10.5px] leading-[1.55] text-ink/70 whitespace-pre-wrap overflow-hidden max-h-40 mb-3">
            {selectedStrategy.dslCode}
          </pre>
        )}

        {/* Date range */}
        <div className="mb-3">
          <label className={fieldLabel}>Date Range</label>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="date"
              aria-label="Start date"
              value={config.startDate}
              onChange={(e) => setConfig({ startDate: e.target.value })}
              className={`${controlBox} font-mono text-[13px] outline-none focus:border-orange-500`}
            />
            <input
              type="date"
              aria-label="End date"
              value={config.endDate}
              onChange={(e) => setConfig({ endDate: e.target.value })}
              className={`${controlBox} font-mono text-[13px] outline-none focus:border-orange-500`}
            />
          </div>
          <div className="flex gap-1.5 mt-2">
            {RANGE_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setConfig({ startDate: shiftYears(config.endDate, preset.years) })}
                className={`font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px] transition-colors ${
                  activePreset === preset.label ? 'bg-ink text-bone' : 'bg-paper hover:bg-bone'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Initial capital */}
        <div className="mb-3">
          <label htmlFor="bt-capital" className={fieldLabel}>Initial Capital</label>
          <div className={`${controlBox} font-mono text-[15px] font-bold`}>
            <span className="flex items-center gap-1">
              <span className="text-ink/50">$</span>
              <input
                id="bt-capital"
                type="number"
                min={0}
                step={1000}
                value={config.initialCapital}
                onChange={(e) => setConfig({ initialCapital: parseFloat(e.target.value) || 0 })}
                className="bg-transparent outline-none w-full tabular-nums"
              />
            </span>
            <span className="font-mono text-[11px] text-ink/50">USD</span>
          </div>
        </div>

        {/* Benchmark + commission */}
        <div className="grid grid-cols-2 gap-2 mb-4">
          <div>
            <label htmlFor="bt-benchmark" className={fieldLabel}>Benchmark</label>
            <div className="relative">
              <select
                id="bt-benchmark"
                value={config.benchmarkSymbol}
                onChange={(e) => setConfig({ benchmarkSymbol: e.target.value })}
                className={`${controlBox} w-full appearance-none pr-7 font-mono text-[13px] outline-none focus:border-orange-500`}
              >
                <option value="">None</option>
                {BENCHMARKS.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink/60 pointer-events-none" />
            </div>
          </div>
          <div>
            <label htmlFor="bt-commission" className={fieldLabel}>Commission</label>
            <div className={`${controlBox} font-mono text-[13px]`}>
              <span className="flex items-center gap-1">
                <span className="text-ink/50">$</span>
                <input
                  id="bt-commission"
                  type="number"
                  min={0}
                  step={0.001}
                  value={config.commission}
                  onChange={(e) => setConfig({ commission: parseFloat(e.target.value) || 0 })}
                  className="bg-transparent outline-none w-full tabular-nums"
                />
              </span>
              <span className="font-mono text-[10px] text-ink/50">/sh</span>
            </div>
          </div>
        </div>

        {/* Run */}
        <button
          type="button"
          onClick={onRun}
          disabled={!canRun}
          className="w-full border-2 border-ink bg-orange-500 shadow-[4px_4px_0_#0d0d0d] py-3.5 font-display uppercase text-[22px] tracking-[0.02em] flex items-center justify-center gap-2.5 transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[6px_6px_0_#0d0d0d] active:translate-x-0 active:translate-y-0 active:shadow-[2px_2px_0_#0d0d0d] disabled:opacity-50 disabled:shadow-[4px_4px_0_#0d0d0d] disabled:translate-x-0 disabled:translate-y-0 disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <Loader2 className="w-[18px] h-[18px] animate-spin" />
              Running
            </>
          ) : (
            <>
              <Play className="w-[18px] h-[18px] fill-ink" />
              Run Backtest
            </>
          )}
        </button>

        {lastRunLabel && (
          <div className="mt-2.5 text-center font-mono text-[10px] uppercase tracking-[0.06em] text-ink/50">
            {lastRunLabel}
          </div>
        )}
      </div>
    </div>
  );
}
