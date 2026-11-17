import { useEffect, useRef } from 'react';

import { sourcesSummary, type SourceView } from './sources';

export function CitationMark({
  n,
  active = false,
  onClick,
}: {
  n: number;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Source ${n}`}
      className={`inline-grid h-[17px] min-w-[17px] place-items-center rounded-[4px] px-1 align-[1px] font-mono text-[10.5px] font-semibold ${
        active
          ? 'bg-accent text-canvas'
          : 'bg-accent-soft text-accent hover:bg-accent hover:text-canvas'
      }`}
    >
      {n}
    </button>
  );
}

export function SourceCard({ source, active }: { source: SourceView; active: boolean }) {
  return (
    <article
      id={`source-${source.n}`}
      aria-label={`Source ${source.n}: ${source.title}`}
      className={`grid min-w-0 gap-2 rounded-panel border bg-panel px-3.5 py-3 ${
        active
          ? 'border-accent/60 shadow-[0_0_0_3px_var(--accent-soft)]'
          : source.ok
            ? 'border-line'
            : 'border-risk-line'
      }`}
    >
      <div className="flex items-center gap-2">
        <CitationMark n={source.n} active={active} />
        <b className="min-w-0 flex-1 truncate font-mono text-[12px] font-medium text-fg-2">
          {source.tool}
        </b>
        {source.seconds !== null && (
          <span className="num flex-none text-[11.5px] text-fg-3">
            {source.seconds.toFixed(1)} s
          </span>
        )}
      </div>
      <div className="text-[13px] font-medium text-fg">{source.title}</div>
      {source.rows.length > 0 && (
        <dl className="m-0 grid gap-1 text-[12.5px]">
          {source.rows.map((r, i) => (
            <div key={`${r.label}-${i}`} className="flex items-baseline justify-between gap-3">
              <dt className="text-fg-3">{r.label}</dt>
              <dd className="num m-0 min-w-0 truncate text-right text-fg">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {source.code.length > 0 && (
        <pre className="m-0 overflow-x-auto rounded-[7px] bg-sunk px-2.5 py-2 font-mono text-[11.5px] leading-[1.65]">
          {source.code.map((line, i) => (
            <div key={i} className="flex gap-3">
              <span className="w-4 flex-none select-none text-right text-fg-3">{i + 1}</span>
              <code className="whitespace-pre">{line}</code>
            </div>
          ))}
          {source.moreLines > 0 && (
            <div className="pl-7 text-fg-3">
              {source.moreLines} more {source.moreLines === 1 ? 'line' : 'lines'}
            </div>
          )}
        </pre>
      )}
      {source.note && <p className="m-0 text-[12px] text-fg-3">{source.note}</p>}
    </article>
  );
}

/** What each of Copilot's tool calls in this thread returned, numbered as cited (conversation B). */
export function SourcesPane({
  sources,
  active,
  className = '',
}: {
  sources: readonly SourceView[];
  active: number | null;
  className?: string;
}) {
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (active === null) return;
    list.current
      ?.querySelector(`#source-${active}`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [active]);

  return (
    <aside aria-label="What Copilot read" className={`flex min-h-0 flex-col ${className}`}>
      <div className="flex flex-none items-baseline justify-between gap-3 border-b border-line px-5 py-[15px]">
        <b className="text-[14px] font-semibold">What Copilot read</b>
        {sources.length > 0 && (
          <span className="text-[12px] text-fg-3">{sourcesSummary(sources)}</span>
        )}
      </div>
      <div ref={list} className="grid min-h-0 flex-1 content-start gap-3 overflow-y-auto p-4">
        {sources.length === 0 ? (
          <p className="m-0 text-[12.5px] text-fg-3">
            When Copilot reads a strategy, a backtest or your positions to answer, what it read
            shows here, numbered so you can check each part of the answer.
          </p>
        ) : (
          sources.map((s) => (
            <SourceCard key={`${s.n}-${s.id}`} source={s} active={s.n === active} />
          ))
        )}
      </div>
    </aside>
  );
}
