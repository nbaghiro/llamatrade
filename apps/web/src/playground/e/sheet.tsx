import { useState, type ReactNode } from 'react';

import { AskLine } from './ask';
import { PerfChart } from './chart';
import { dayLabel, monthLabel, RANGES, tone, type Range } from './model';
import type { Scope } from './scope';
import { Mono, Panel, Segmented } from './ui';

/**
 * One sheet per page: the Ask line and a compact chart, both about the row selected in the tree
 * below them, then the tree itself.
 */
export function ScopeSheet({
  scope,
  children,
  chartHeight = 272,
}: {
  scope: Scope;
  children: ReactNode;
  chartHeight?: number;
}) {
  const [range, setRange] = useState<Range>('3M');
  const w = scope.window(range);
  const figs = scope.figures(w);
  const n = w.dates.length;
  const fmt =
    w.dates[n - 1].getTime() - w.dates[0].getTime() > 200 * 86_400_000 ? monthLabel : dayLabel;
  return (
    <Panel className="overflow-hidden">
      <div className="border-b border-line px-4 py-4 md:px-6">
        <AskLine
          context={scope.ask.context}
          placeholder={scope.ask.placeholder}
          suggestions={scope.ask.suggestions}
        />
      </div>
      <div className="px-4 pb-4 pt-5 md:px-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <nav aria-label="Scope" className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            {scope.path.map((p, i) => (
              <span key={i} className="inline-flex items-center gap-2">
                {i > 0 && <span className="text-fg-3">/</span>}
                <Mono className={i === scope.path.length - 1 ? 'text-fg' : 'text-fg-3'}>{p}</Mono>
              </span>
            ))}
          </nav>
          {scope.ranged ? (
            <Segmented
              label="Range"
              value={range}
              onChange={setRange}
              options={RANGES.map((r) => ({ key: r, label: r }))}
            />
          ) : (
            <span className="font-mono text-[11px] tabular-nums text-fg-3">
              {fmt(w.dates[0])} to {fmt(w.dates[n - 1])}
            </span>
          )}
        </div>
        <div className="grid gap-6 md:grid-cols-[248px_minmax(0,1fr)]">
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold tracking-[-0.01em] text-fg">
              {scope.title}
            </div>
            {scope.value !== undefined && (
              <div className="mt-2 font-mono text-[30px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg">
                $
                {scope.value.toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
            )}
            <div className="mt-2 min-h-[18px] font-mono text-[12px] tabular-nums">
              {scope.today !== undefined && Math.abs(scope.today) > 0.005 ? (
                <span className={tone(scope.today)}>
                  {scope.today > 0 ? '+' : '−'}${Math.abs(scope.today).toFixed(2)} today
                </span>
              ) : (
                <span className="text-fg-3">{scope.note ?? ''}</span>
              )}
            </div>
            {scope.note && scope.today !== undefined && Math.abs(scope.today) > 0.005 && (
              <div className="mt-1 truncate text-[12px] text-fg-3">{scope.note}</div>
            )}
            <dl className="m-0 mt-4 border-t border-line">
              {figs.map((f) => (
                <div
                  key={f.label}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 border-b border-line py-2"
                >
                  <dt className="text-[12px] text-fg-3">{f.label}</dt>
                  <dd
                    className={`m-0 text-right font-mono text-[15px] tabular-nums ${f.tone !== undefined ? tone(f.tone) : 'text-fg'}`}
                  >
                    {f.value}
                  </dd>
                  {f.sub && (
                    <dd className="col-span-2 m-0 truncate text-right font-mono text-[10.5px] text-fg-3">
                      {f.sub}
                    </dd>
                  )}
                </div>
              ))}
            </dl>
          </div>
          <div className="min-w-0">
            <PerfChart
              key={scope.key}
              w={w}
              height={chartHeight}
              mainLabel={scope.mainLabel}
              drawdownStrip={false}
            />
          </div>
        </div>
      </div>
      <div className="border-t border-line">{children}</div>
    </Panel>
  );
}
