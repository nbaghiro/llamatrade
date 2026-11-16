import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { DEFAULT_BACKTEST_COSTS, type BacktestConfig } from '@llamatrade/core/stores/backtest';
import { ChevronDown } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { formatMoney, formatPct } from '../../lib/format';
import { Popover } from '../ui/Popover';

interface RunSentenceProps {
  config: BacktestConfig;
  strategies: readonly Strategy[];
  onChange: (patch: Partial<BacktestConfig>) => void;
  /** Values can't change while a run is in flight. */
  locked?: boolean;
  /** The run or cancel button and any state beside it. */
  end: ReactNode;
}

const PRESETS = [
  ['1Y', 1],
  ['2Y', 2],
  ['3Y', 3],
  ['5Y', 5],
] as const;

const iso = (d: Date) => d.toISOString().slice(0, 10);

function yearsBack(end: string, years: number): string {
  const d = new Date(`${end}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - years);
  return iso(d);
}

const tokenBase =
  'inline-flex h-[30px] items-center gap-1.5 whitespace-nowrap rounded px-2.5 text-[13px] text-fg ring-1 ring-inset transition-colors disabled:cursor-not-allowed disabled:opacity-60';

function tokenClass(numeric: boolean, changed = false) {
  return `${tokenBase} ${numeric ? 'font-mono font-normal' : 'font-medium'} ${
    changed ? 'bg-accent-soft ring-accent/50' : 'bg-sunk ring-line-strong hover:ring-fg-3'
  }`;
}

/** One token in the sentence: a value that opens a popover to edit it. */
function Token({
  label,
  value,
  numeric = false,
  select = false,
  changed = false,
  locked,
  width = 280,
  children,
}: {
  label: string;
  value: ReactNode;
  numeric?: boolean;
  select?: boolean;
  changed?: boolean;
  locked: boolean;
  width?: number;
  children: (close: () => void) => ReactNode;
}) {
  return (
    <Popover
      align="left"
      width={width}
      label={label}
      trigger={(p) => (
        <button
          type="button"
          {...p}
          disabled={locked}
          aria-label={`${label}: ${typeof value === 'string' ? value : ''}`}
          className={tokenClass(numeric, changed)}
        >
          {value}
          {select && <ChevronDown className="h-3 w-3 text-fg-3" aria-hidden="true" />}
        </button>
      )}
    >
      {(close) => <div className="grid gap-3 p-3">{children(close)}</div>}
    </Popover>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-medium text-fg-2">{label}</span>
      {children}
    </label>
  );
}

/** Commits a draft number on Enter or on Done. */
function NumberEditor({
  label,
  initial,
  min,
  step,
  prefix,
  suffix,
  onDone,
}: {
  label: string;
  initial: number;
  min: number;
  step: number;
  prefix?: string;
  suffix?: string;
  onDone: (v: number) => void;
}) {
  const [draft, setDraft] = useState(String(initial));
  const v = Number(draft);
  const ok = draft.trim() !== '' && Number.isFinite(v) && v >= min;
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (ok) onDone(v);
      }}
    >
      <Field label={label}>
        <span className="flex items-center gap-1.5">
          {prefix && <span className="text-fg-3">{prefix}</span>}
          <input
            autoFocus
            type="number"
            inputMode="decimal"
            min={min}
            step={step}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className={`input num ${ok ? '' : 'input-error'}`}
          />
          {suffix && <span className="whitespace-nowrap text-fg-3">{suffix}</span>}
        </span>
      </Field>
      <button type="submit" disabled={!ok} className="btn btn-primary btn-sm justify-self-end">
        Done
      </button>
    </form>
  );
}

/** Backtest setup as one editable sentence: each value is a token with a popover. */
export function RunSentence({
  config,
  strategies,
  onChange,
  locked = false,
  end,
}: RunSentenceProps) {
  const strategy = strategies.find((s) => s.id === config.strategyId);
  const version = config.strategyVersion || strategy?.version || 0;
  const costsChanged =
    config.commission !== DEFAULT_BACKTEST_COSTS.commission ||
    config.slippage !== DEFAULT_BACKTEST_COSTS.slippage;
  const word = 'text-[14px] text-fg-2';

  return (
    <div className="flex flex-wrap items-center gap-2 text-[14px]">
      <span className={word}>Run</span>
      <Token
        label="Strategy"
        select
        locked={locked}
        width={320}
        value={strategy ? `${strategy.name} · version ${version}` : 'Choose a strategy'}
      >
        {(close) =>
          strategies.length === 0 ? (
            <p className="m-0 text-[12.5px] text-fg-2">
              No strategies yet. Create one in Strategies, then come back to run it.
            </p>
          ) : (
            <>
              <ul
                className="m-0 grid max-h-[260px] list-none gap-0.5 overflow-y-auto p-0"
                role="listbox"
              >
                {strategies.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={s.id === config.strategyId}
                      onClick={() => {
                        onChange({ strategyId: s.id, strategyVersion: s.version });
                        close();
                      }}
                      className={`flex w-full items-center justify-between gap-3 rounded-[6px] px-2 py-1.5 text-left text-[13px] hover:bg-sunk ${
                        s.id === config.strategyId ? 'bg-accent-soft text-fg' : 'text-fg-2'
                      }`}
                    >
                      <span className="truncate">{s.name}</span>
                      <span className="num text-[11.5px] text-fg-3">v{s.version}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {strategy && strategy.version > 1 && (
                <Field label="Version">
                  <select
                    className="select"
                    value={version}
                    onChange={(e) => onChange({ strategyVersion: Number(e.target.value) })}
                  >
                    {Array.from({ length: strategy.version }, (_, i) => strategy.version - i).map(
                      (v) => (
                        <option key={v} value={v}>
                          Version {v}
                          {v === strategy.version ? ' (current)' : ''}
                        </option>
                      )
                    )}
                  </select>
                </Field>
              )}
            </>
          )
        }
      </Token>
      <span className={word}>from</span>
      <Token label="Start date" numeric locked={locked} value={config.startDate}>
        {(close) => (
          <>
            <div className="flex gap-1" role="group" aria-label="Range ending on the end date">
              {PRESETS.map(([k, y]) => (
                <button
                  key={k}
                  type="button"
                  className="btn btn-secondary btn-sm flex-1"
                  onClick={() => {
                    onChange({ startDate: yearsBack(config.endDate, y) });
                    close();
                  }}
                >
                  {k}
                </button>
              ))}
            </div>
            <Field label="Start date">
              <input
                type="date"
                className="input num"
                value={config.startDate}
                max={config.endDate}
                onChange={(e) => e.target.value && onChange({ startDate: e.target.value })}
              />
            </Field>
          </>
        )}
      </Token>
      <span className={word}>to</span>
      <Token label="End date" numeric locked={locked} value={config.endDate}>
        {() => (
          <Field label="End date">
            <input
              type="date"
              className="input num"
              value={config.endDate}
              min={config.startDate}
              max={iso(new Date())}
              onChange={(e) => e.target.value && onChange({ endDate: e.target.value })}
            />
          </Field>
        )}
      </Token>
      <span className={word}>with</span>
      <Token
        label="Starting capital"
        numeric
        locked={locked}
        value={formatMoney(config.initialCapital, { dp: 0 })}
      >
        {(close) => (
          <NumberEditor
            label="Starting capital"
            initial={config.initialCapital}
            min={100}
            step={1000}
            prefix="$"
            onDone={(v) => {
              onChange({ initialCapital: v });
              close();
            }}
          />
        )}
      </Token>
      <span className={word}>against</span>
      <Token
        label="Benchmark"
        select
        locked={locked}
        value={config.benchmarkSymbol || 'no benchmark'}
        width={240}
      >
        {(close) => (
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const v = new FormData(e.currentTarget).get('symbol');
              onChange({
                benchmarkSymbol: String(v ?? '')
                  .trim()
                  .toUpperCase(),
              });
              close();
            }}
          >
            <Field label="Benchmark symbol">
              <input
                autoFocus
                name="symbol"
                defaultValue={config.benchmarkSymbol}
                placeholder="SPY"
                maxLength={8}
                className="input num uppercase"
              />
            </Field>
            <span className="text-[11.5px] text-fg-3">Leave it empty to run without one.</span>
            <button type="submit" className="btn btn-primary btn-sm justify-self-end">
              Done
            </button>
          </form>
        )}
      </Token>
      <Popover
        align="left"
        width={300}
        label="Commission and fills"
        trigger={(p) =>
          costsChanged ? (
            <button type="button" {...p} disabled={locked} className={tokenClass(true, true)}>
              {formatMoney(config.commission, { dp: 3 })} a fill ·{' '}
              {formatPct(config.slippage, { dp: 2 })} slippage
            </button>
          ) : (
            <button
              type="button"
              {...p}
              disabled={locked}
              className="btn btn-ghost btn-sm px-1.5 text-accent hover:text-accent disabled:opacity-60"
            >
              Commission and fills
            </button>
          )
        }
      >
        {(close) => (
          <div className="grid gap-3 p-3">
            <Field label="Commission, flat per fill">
              <span className="flex items-center gap-1.5">
                <span className="text-fg-3">$</span>
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className="input num"
                  defaultValue={config.commission}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (e.target.value !== '' && Number.isFinite(v) && v >= 0)
                      onChange({ commission: v });
                  }}
                />
              </span>
            </Field>
            <Field label="Slippage">
              <span className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={0}
                  max={5}
                  step={0.01}
                  className="input num"
                  defaultValue={Number((config.slippage * 100).toFixed(4))}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (e.target.value !== '' && Number.isFinite(v) && v >= 0)
                      onChange({ slippage: v / 100 });
                  }}
                />
                <span className="text-fg-3">%</span>
              </span>
            </Field>
            <p className="m-0 text-[11.5px] text-fg-3">
              Orders fill at the close, moved by the slippage, on the same engine as paper sessions.
            </p>
            {costsChanged && (
              <button
                type="button"
                className="btn btn-ghost btn-sm justify-self-start px-1.5"
                onClick={() => {
                  onChange({
                    commission: DEFAULT_BACKTEST_COSTS.commission,
                    slippage: DEFAULT_BACKTEST_COSTS.slippage,
                  });
                  close();
                }}
              >
                Use the defaults
              </button>
            )}
          </div>
        )}
      </Popover>
      <span className="ml-auto flex items-center gap-2.5">{end}</span>
    </div>
  );
}
