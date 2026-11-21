import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { TreeBar, TreeRow, type TreeRowMark } from '../../components/ui/TreeRow';
import { collapse, guidesOf, withKids } from '../../lib/outlineTree';

import { money0, pts, tone } from './model';
import type { Scope } from './scope';
import { Spark } from './ui';

export interface Col {
  key: string;
  label: string;
  width: number;
  align?: 'right';
  /** Shown on phones too. */
  keep?: boolean;
}

export interface LRow {
  id: string;
  depth: number;
  type: string;
  label: ReactNode;
  cells?: Record<string, ReactNode>;
  /** Replaces the cells, e.g. a Copilot row's actions. */
  end?: ReactNode;
  live?: boolean;
  mark?: TreeRowMark;
  muted?: boolean;
  strong?: boolean;
  scope?: Scope;
  to?: string;
}

function Arrow() {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true" className="h-3 w-3">
      <path
        d="M3 9l6-6M4.5 3H9v4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const PHONE = '(max-width: 640px)';

function usePhone(): boolean {
  const [phone, setPhone] = useState(() => window.matchMedia(PHONE).matches);
  useEffect(() => {
    const m = window.matchMedia(PHONE);
    const on = () => setPhone(m.matches);
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, []);
  return phone;
}

const cellClass = (c: Col) =>
  `${c.keep ? 'flex' : 'hidden md:flex'} items-center ${c.align === 'right' ? 'justify-end' : ''} min-w-0`;

/**
 * The account drawn as one outline: guide lines, mono type labels and the live path in ink, with
 * ledger columns at the right of every row. Selecting a row hands its scope to the chart above.
 */
export function LedgerTree({
  rows,
  cols,
  name = 'Name',
  selected,
  onSelect,
  closedAtStart = [],
  phoneDepth = 2,
  label,
}: {
  rows: LRow[];
  cols: Col[];
  name?: string;
  selected?: string | null;
  onSelect?: (r: LRow) => void;
  closedAtStart?: string[];
  /** On phones, rows at this depth and below start folded. */
  phoneDepth?: number;
  label: string;
}) {
  const nav = useNavigate();
  const phone = usePhone();
  const [closed, setClosed] = useState<Set<string>>(() => {
    const out = new Set(closedAtStart);
    if (window.matchMedia(PHONE).matches)
      withKids(rows).forEach((r) => r.kids && r.depth >= phoneDepth && out.add(r.id));
    return out;
  });
  const shown = useMemo(() => {
    const flat = withKids(rows.map((r) => ({ ...r, live: !!r.live })));
    const vis = collapse(flat, closed);
    const gs = guidesOf(vis);
    return vis.map((r, i) => ({ r, g: gs[i] }));
  }, [rows, closed]);
  const toggle = (id: string) =>
    setClosed((c) => {
      const n = new Set(c);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const anyLink = rows.some((r) => r.to);

  return (
    <div role="tree" aria-label={label} className="min-w-0">
      <div className="flex h-9 items-center border-b border-line pr-4 text-[11.5px] font-medium text-fg-3">
        <span className="w-[30px] flex-none" />
        <span className="min-w-0 flex-1">{name}</span>
        <span className="ml-3 flex flex-none items-center gap-3">
          {cols.map((c) => (
            <span
              key={c.key}
              className={`${cellClass(c)} ${c.align === 'right' ? 'text-right' : ''}`}
              style={{ width: c.width }}
            >
              {c.label}
            </span>
          ))}
          {anyLink && <span className="hidden w-5 md:block" />}
        </span>
      </div>
      {shown.map(({ r, g }) => (
        <TreeRow
          key={r.id}
          guides={g}
          type={phone ? '' : r.type}
          typeWidth={phone ? 0 : 72}
          closed={r.kids ? closed.has(r.id) : undefined}
          onToggle={() => toggle(r.id)}
          hiddenCount={r.hidden}
          live={r.live}
          mark={r.mark}
          muted={r.muted}
          selected={selected === (r.scope?.key ?? r.id)}
          onClick={() => onSelect?.(r)}
          onDoubleClick={() => r.to && nav(r.to)}
          phraseClass={r.strong ? 'font-medium' : ''}
          end={
            r.end ?? (
              <>
                {cols.map((c) => (
                  <span key={c.key} className={cellClass(c)} style={{ width: c.width }}>
                    {r.cells?.[c.key]}
                  </span>
                ))}
                {anyLink && (
                  <span className="hidden w-5 md:block">
                    {r.to && (
                      <Link
                        to={r.to}
                        aria-label="Open"
                        onClick={(e) => e.stopPropagation()}
                        className="grid h-5 w-5 place-items-center rounded-[4px] text-fg-3 hover:bg-line hover:text-fg"
                      >
                        <Arrow />
                      </Link>
                    )}
                  </span>
                )}
              </>
            )
          }
        >
          {r.label}
        </TreeRow>
      ))}
    </div>
  );
}

/* ---------- Cells ---------- */

export const Money = ({ v, muted }: { v?: number; muted?: boolean }) =>
  v === undefined ? (
    <span className="font-mono text-fg-3">·</span>
  ) : (
    <span className={`font-mono tabular-nums ${muted ? 'text-fg-3' : 'text-fg'}`}>
      {v.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
    </span>
  );

export const Change = ({ v }: { v?: number }) =>
  v === undefined || Math.abs(v) < 0.005 ? (
    <span className="font-mono text-fg-3">·</span>
  ) : (
    <span className={`font-mono tabular-nums ${tone(v)}`}>
      {v > 0 ? '+' : '−'}
      {Math.abs(v) >= 1000 ? money0(Math.abs(v)) : `$${Math.abs(v).toFixed(2)}`}
    </span>
  );

export const Pct = ({ v, toned = true }: { v?: number; toned?: boolean }) =>
  v === undefined ? (
    <span className="font-mono text-fg-3">·</span>
  ) : (
    <span className={`font-mono tabular-nums ${toned ? tone(v) : 'text-fg-2'}`}>{pts(v)}</span>
  );

export const Trend = ({ values, bench }: { values?: number[]; bench?: number[] }) =>
  values && values.length > 1 ? (
    <span className="flex w-full items-center justify-between gap-2">
      <Spark values={values} bench={bench} width={60} height={18} />
      <Pct v={values[values.length - 1] - values[0]} />
    </span>
  ) : (
    <span className="font-mono text-fg-3">·</span>
  );

export const Weight = ({
  pct,
  live,
  muted,
  pick,
  text,
}: {
  pct?: number;
  live?: boolean;
  muted?: boolean;
  pick?: boolean;
  text?: string;
}) =>
  pct === undefined && !pick ? null : (
    <span className="flex w-full items-center justify-between gap-2">
      <TreeBar pct={pct} live={live} muted={muted} pick={pick} width={56} />
      <span className={`font-mono tabular-nums ${muted ? 'text-fg-3' : 'text-fg-2'}`}>
        {text ?? (pick ? 'pick' : `${(pct ?? 0).toFixed(pct !== undefined && pct < 10 ? 1 : 0)}%`)}
      </span>
    </span>
  );
