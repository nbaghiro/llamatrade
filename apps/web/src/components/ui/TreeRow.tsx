import type { HTMLAttributes, ReactNode } from 'react';

import type { Guide } from '../../lib/outlineTree';

export type TreeRowMark = 'add' | 'del';

export interface TreeRowState {
  /** On the path in effect today, drawn in ink. */
  live?: boolean;
  selected?: boolean;
  /** Hovered from elsewhere, e.g. a chart or a list beside the tree. */
  hot?: boolean;
  /** Kept on, e.g. a row whose line stays on a chart. */
  pinned?: boolean;
  muted?: boolean;
  mark?: TreeRowMark;
  flag?: 'error' | 'warning';
}

function Chevron({ closed }: { closed: boolean }) {
  return (
    <svg
      viewBox="0 0 10 10"
      aria-hidden="true"
      className={`h-2.5 w-2.5 transition-transform ${closed ? '-rotate-90' : ''}`}
    >
      <path
        d="M2 3.5l3 3 3-3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const line = 'absolute left-[10px] w-px bg-line-strong';
const liveLine = 'absolute left-[9.75px] w-[1.5px] bg-fg';

function GuideCell({ g }: { g: Guide }) {
  return (
    <span aria-hidden="true" className="relative h-full w-[22px] flex-none">
      {(g.elbow || g.down) && <i className={`${g.liveUp ? liveLine : line} top-0 h-1/2`} />}
      {g.down && <i className={`${g.liveDown ? liveLine : line} bottom-0 top-1/2`} />}
      {g.elbow && (
        <i
          className={`absolute top-1/2 ${g.liveAcross ? 'left-[9.75px] -mt-px h-[1.5px] w-[10.25px] bg-fg' : 'left-[10px] h-px w-[10px] bg-line-strong'}`}
        />
      )}
    </span>
  );
}

function rowTone({ selected, hot, pinned, mark }: TreeRowState): string {
  if (mark === 'add')
    return selected
      ? 'bg-[color-mix(in_srgb,rgb(var(--accent))_12%,rgb(var(--panel)))]'
      : 'bg-[color-mix(in_srgb,rgb(var(--accent))_7%,rgb(var(--panel)))]';
  if (selected) return 'bg-sunk shadow-[inset_0_0_0_1px_rgb(var(--line-strong))]';
  if (pinned) return 'bg-sunk';
  if (hot) return 'bg-sunk/75';
  return 'hover:bg-sunk/70';
}

const GUTTER_TONE = {
  add: 'text-accent',
  del: 'text-fg-3',
  error: 'text-loss',
  warning: 'text-risk',
} as const;

export interface TreeRowProps
  extends TreeRowState, Omit<HTMLAttributes<HTMLDivElement>, 'className' | 'children'> {
  guides: readonly Guide[];
  /** Whether the row's children are hidden; undefined for a row without children. */
  closed?: boolean;
  onToggle?: () => void;
  /** The mono label: STRATEGY, IF, WEIGHT, SESSION and so on. */
  type: string;
  hiddenCount?: number;
  /** What sits at the right end: a weight bar, figures or a marker. */
  end?: ReactNode;
  /** Extra classes for the phrase, e.g. a heavier weight on a top-level row. */
  phraseClass?: string;
  /** Width of the type label column. */
  typeWidth?: number;
  children: ReactNode;
}

/** One row of an outline tree: gutter mark, guide lines, caret, type label, phrase and end. */
export function TreeRow({
  guides,
  closed,
  onToggle,
  type,
  hiddenCount = 0,
  end,
  phraseClass = '',
  typeWidth = 72,
  children,
  live,
  selected,
  hot,
  pinned,
  muted,
  mark,
  flag,
  ...rest
}: TreeRowProps) {
  const removed = mark === 'del';
  const gutter = mark === 'add' ? '+' : mark === 'del' ? '−' : flag ? '!' : '';
  const gutterTone = GUTTER_TONE[mark ?? flag ?? 'add'];
  const accentBar = mark === 'add' || pinned;
  return (
    <div
      {...rest}
      aria-expanded={closed === undefined ? undefined : !closed}
      className={`relative flex h-8 cursor-pointer items-center pr-4 text-[14px] ${rowTone({ selected, hot, pinned, mark })}`}
    >
      {accentBar && (
        <span
          aria-hidden="true"
          className={`absolute inset-y-0 left-0 w-0.5 ${mark === 'add' ? 'bg-accent' : 'bg-fg'}`}
        />
      )}
      <span
        aria-hidden="true"
        className={`w-[30px] flex-none text-center font-mono text-[13px] font-medium ${gutterTone}`}
      >
        {gutter}
      </span>
      {guides.map((g, i) => (
        <GuideCell key={i} g={g} />
      ))}
      {closed !== undefined ? (
        <button
          type="button"
          aria-label={closed ? 'Expand' : 'Collapse'}
          tabIndex={-1}
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.();
          }}
          className="grid h-5 w-[22px] flex-none place-items-center rounded-[3px] text-fg-3 hover:bg-line hover:text-fg"
        >
          <Chevron closed={closed} />
        </button>
      ) : (
        <span aria-hidden="true" className="grid w-[22px] flex-none place-items-center">
          <i className={`h-[5px] w-[5px] rounded-full ${live ? 'bg-fg' : 'bg-line-strong'}`} />
        </span>
      )}
      <span
        className={`ml-1 flex-none font-mono text-[10.5px] font-medium uppercase leading-none tracking-[0.08em] ${
          removed ? 'text-fg-3 line-through' : live ? 'text-fg' : 'text-fg-3'
        }`}
        style={{ width: typeWidth }}
      >
        {type}
      </span>
      <span
        className={`min-w-0 flex-1 truncate first-letter:uppercase ${
          removed ? 'text-fg-3 line-through decoration-fg-3' : muted ? 'text-fg-3' : 'text-fg'
        } ${phraseClass}`}
      >
        {children}
        {hiddenCount > 0 && (
          <span className="ml-2 text-[12.5px] text-fg-3">{hiddenCount} hidden</span>
        )}
      </span>
      {end !== undefined && (
        <span className="ml-3 flex flex-none items-center gap-3 text-[12.5px] text-fg-3">
          {end}
        </span>
      )}
    </div>
  );
}

/** A ticker set in mono on a soft chip. */
export function Ticker({ symbol, on }: { symbol: string; on?: boolean }) {
  return (
    <span
      className={`inline-block rounded-[3px] px-[5px] font-mono text-[0.86em] font-medium leading-[1.35] ${
        on ? 'bg-fg text-panel' : 'bg-sunk text-fg'
      }`}
    >
      {symbol}
    </span>
  );
}

/** A share of a parent as a short bar; `pick` draws the dashed bar for a filter's candidates. */
export function TreeBar({
  pct,
  live,
  muted,
  width = 120,
  pick,
}: {
  pct?: number;
  live?: boolean;
  muted?: boolean;
  width?: number;
  pick?: boolean;
}) {
  const fill = muted ? 'bg-fg-3/50' : live ? 'bg-accent' : 'bg-fg-2';
  return (
    <span
      aria-hidden="true"
      className="block h-[5px] flex-none overflow-hidden rounded-[3px] bg-sunk"
      style={{ width }}
    >
      {pick ? (
        <i
          className="block h-full w-full"
          style={{
            background: `repeating-linear-gradient(90deg, rgb(var(${live ? '--accent' : '--fg-3'}) / ${live ? 1 : 0.55}) 0 4px, transparent 4px 7px)`,
          }}
        />
      ) : (
        <i
          className={`block h-full rounded-[3px] ${fill}`}
          style={{ width: `${Math.max(0, Math.min(100, pct ?? 0))}%` }}
        />
      )}
    </span>
  );
}

/** The pill on the branch a running session follows today. */
export function LiveMarker({ children = 'Live today' }: { children?: ReactNode }) {
  return (
    <span className="inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-full border border-fg px-[9px] text-[12px] font-medium text-fg">
      <i aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-gain" />
      {children}
    </span>
  );
}
