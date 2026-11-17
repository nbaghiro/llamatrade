import type { CSSProperties, ReactNode } from 'react';

/**
 * The marks the annotated curve and its lanes use, one glyph per meaning:
 * ring (a rebalance or a buy), dot (a fill or a sell, numbered when it carries a count),
 * planned (scheduled, not yet happened), start and stop (a session's ends),
 * diamond and diamondFilled (versions, deposits, dividends), muted (a reference run).
 */
export type MarkerShape =
  | 'ring'
  | 'dot'
  | 'planned'
  | 'start'
  | 'stop'
  | 'diamond'
  | 'diamondFilled'
  | 'muted';

export type MarkerTone = 'accent' | 'risk' | 'muted';

interface LaneMarkerProps {
  shape: MarkerShape;
  tone?: MarkerTone;
  /** A number inside a dot, such as how many fills it stands for. */
  count?: number;
  /** Positioned glyphs are centred on their point; static ones sit inline. */
  positioned?: boolean;
  style?: CSSProperties;
  title?: string;
}

const COLOR: Record<MarkerTone, string> = {
  accent: 'rgb(var(--accent))',
  risk: 'rgb(var(--risk))',
  muted: 'rgb(var(--fg-3))',
};

function glyphStyle(shape: MarkerShape, tone: MarkerTone, count?: number): CSSProperties {
  const c = COLOR[tone];
  switch (shape) {
    case 'ring':
      return { width: 10, height: 10, borderRadius: 999, border: `1.5px solid ${c}` };
    case 'dot':
      return count !== undefined
        ? { width: 16, height: 16, borderRadius: 999, background: c }
        : { width: 10, height: 10, borderRadius: 999, background: c };
    case 'planned':
      return {
        width: 10,
        height: 10,
        borderRadius: 999,
        border: '1.5px dashed rgb(var(--fg-3))',
      };
    case 'start':
      return { width: 3, height: 14, borderRadius: 2, background: c };
    case 'stop':
      return { width: 9, height: 9, borderRadius: 2, background: 'rgb(var(--fg-3))' };
    case 'diamond':
      return {
        width: 8,
        height: 8,
        border: `1.5px solid ${tone === 'accent' ? 'rgb(var(--fg))' : c}`,
        transform: 'rotate(45deg)',
      };
    case 'diamondFilled':
      return {
        width: 8,
        height: 8,
        background: tone === 'accent' ? 'rgb(var(--fg))' : c,
        transform: 'rotate(45deg)',
      };
    case 'muted':
      return { width: 9, height: 9, borderRadius: 999, background: 'rgb(var(--fg-3))' };
  }
}

/** One lane glyph. Every glyph has a panel-coloured fill so lines behind it break cleanly. */
export function LaneMarker({
  shape,
  tone = 'accent',
  count,
  positioned = false,
  style,
  title,
}: LaneMarkerProps) {
  const own = glyphStyle(shape, tone, count);
  const filled = shape === 'dot' || shape === 'start' || shape === 'stop' || shape === 'muted';
  const base: CSSProperties = {
    boxSizing: 'border-box',
    flex: 'none',
    display: 'inline-grid',
    placeItems: 'center',
    background: filled || shape === 'diamondFilled' ? undefined : 'rgb(var(--panel))',
    ...own,
  };
  const pos: CSSProperties = positioned
    ? {
        position: 'absolute',
        top: '50%',
        marginLeft: -Number(own.width) / 2,
        marginTop: -Number(own.height) / 2,
        zIndex: count ? 3 : 2,
      }
    : {};
  return (
    <i
      aria-hidden={title ? undefined : true}
      title={title}
      className="not-italic"
      style={{ ...base, ...pos, ...style }}
    >
      {count !== undefined && shape === 'dot' && (
        <b className="font-mono text-[9.5px] font-semibold leading-none text-canvas">{count}</b>
      )}
    </i>
  );
}

export interface LegendItem {
  shape: MarkerShape;
  label: ReactNode;
  tone?: MarkerTone;
  count?: number;
}

/** The key under a lane chart: each glyph with what it means here. */
export function LaneLegend({
  items,
  className = '',
}: {
  items: readonly LegendItem[];
  className?: string;
}) {
  if (!items.length) return null;
  return (
    <div
      className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-fg-3 ${className}`}
    >
      {items.map((it, i) => (
        <span key={i} className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <LaneMarker shape={it.shape} tone={it.tone} count={it.count} />
          {it.label}
        </span>
      ))}
    </div>
  );
}
