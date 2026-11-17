import { useMemo, useRef, type CSSProperties, type KeyboardEvent } from 'react';

import { formatMoney } from '../../lib/format';
import { Sparkline } from '../charts';
import { useWidth } from '../charts/useWidth';
import { sleeveColor } from '../portfolio/sleeveView';

import { moveClass, pctText, type MapTile } from './marketsView';
import { arrowDirection, neighbour, tileTint, treemap, type TreemapRect } from './treemap';

interface HoldingsMapProps {
  tiles: readonly MapTile[];
  selected: string;
  onSelect: (symbol: string) => void;
  height: number;
  /** Phone sizing: smaller type, and dollars only on the largest tiles. */
  compact?: boolean;
  /** Daily closes per symbol, drawn inside the selected tile when it has room. */
  sparks?: Readonly<Record<string, readonly number[]>>;
}

type Size = 'big' | 'mid' | 'xs' | 'tiny';

function tileSize(r: TreemapRect, compact: boolean): Size {
  if (r.w < 56 || r.h < 44) return 'tiny';
  if (compact) return r.w >= 150 && r.h >= 80 ? 'big' : 'xs';
  if (r.w >= 220 && r.h >= 150) return 'big';
  if (r.w < 140 || r.h < 86) return 'xs';
  return 'mid';
}

const SYMBOL_SIZE: Record<Size, string> = {
  big: 'text-[22px]',
  mid: 'text-[15px]',
  xs: 'text-[12.5px]',
  tiny: 'text-[10px]',
};
const PCT_SIZE: Record<Size, string> = {
  big: 'text-[16px]',
  mid: 'text-[13px]',
  xs: 'text-[11.5px]',
  tiny: 'hidden',
};

/** Each held symbol as a tile sized by your dollars in it and tinted by today's move. */
export function HoldingsMap({
  tiles,
  selected,
  onSelect,
  height,
  compact = false,
  sparks = {},
}: HoldingsMapProps) {
  const [ref, width] = useWidth<HTMLDivElement>(compact ? 358 : 900);
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const bySymbol = useMemo(() => new Map(tiles.map((t) => [t.symbol, t])), [tiles]);
  const rects = useMemo(
    () =>
      treemap(
        tiles.map((t) => ({ key: t.symbol, value: t.value })),
        width,
        height
      ),
    [tiles, width, height]
  );

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const dir = arrowDirection(e.key);
    if (!dir) return;
    const next = neighbour(rects, i, dir);
    e.preventDefault();
    if (next !== null) buttons.current[next]?.focus();
  };

  return (
    <div
      ref={ref}
      role="group"
      aria-label="Your holdings, sized by dollars and tinted by today's move"
      className="relative"
      style={{ height }}
    >
      {rects.map((r, i) => {
        const t = bySymbol.get(r.key);
        if (!t) return null;
        const size = tileSize(r, compact);
        const tint = tileTint(t.pct);
        const on = t.symbol === selected;
        const sleeves = [...new Map(t.holders.map((h) => [h.index, h])).values()];
        const showValue = compact ? size === 'big' : size === 'big' || size === 'mid';
        const spark = sparks[t.symbol] ?? [];
        const showSpark = on && !compact && size === 'big' && r.h >= 220 && spark.length > 1;
        const value = formatMoney(t.value, { dp: compact ? 0 : 2 });
        const share = t.share !== null ? `${(t.share * 100).toFixed(1)}%` : null;
        return (
          <button
            key={t.symbol}
            ref={(el) => {
              buttons.current[i] = el;
            }}
            type="button"
            data-tone={tint.tone}
            aria-pressed={on}
            aria-label={[
              t.symbol,
              value,
              share && `${share} of equity`,
              t.pct !== null ? `${pctText(t.pct)} today` : 'no price today',
              `held in ${sleeves.length} ${sleeves.length === 1 ? 'sleeve' : 'sleeves'}`,
            ]
              .filter(Boolean)
              .join(', ')}
            onClick={() => onSelect(t.symbol)}
            onKeyDown={(e) => onKey(e, i)}
            className={`tile-tint absolute flex flex-col items-start gap-0.5 overflow-hidden border-2 border-canvas text-left focus-visible:ring-offset-0 ${
              size === 'tiny'
                ? 'px-1 py-2'
                : size === 'xs' || compact
                  ? 'px-[9px] py-2'
                  : 'px-3 py-2.5'
            } ${compact ? 'rounded-[9px]' : 'rounded-[10px]'} ${
              on
                ? 'z-[1] rounded-[12px] shadow-[inset_0_0_0_2px_rgb(var(--accent)),0_0_0_3px_var(--accent-soft)]'
                : 'hover:brightness-[0.97]'
            }`}
            style={
              {
                left: `${(r.x / width) * 100}%`,
                top: `${(r.y / height) * 100}%`,
                width: `${(r.w / width) * 100}%`,
                height: `${(r.h / height) * 100}%`,
                '--tile-s': tint.strength,
              } as CSSProperties
            }
          >
            <span
              className={`font-mono font-semibold leading-tight tracking-[-0.01em] text-fg ${
                compact && size === 'big'
                  ? 'text-[18px]'
                  : compact && size === 'xs'
                    ? 'text-[13px]'
                    : SYMBOL_SIZE[size]
              }`}
            >
              {t.symbol}
            </span>
            {showValue && (
              <span
                className={`num font-medium text-fg-2 ${compact ? 'text-[11px]' : 'text-[12px]'}`}
              >
                {value}
                {share && ` · ${share}`}
              </span>
            )}
            {t.pct !== null && (
              <span
                className={`num font-semibold ${moveClass(t.pct)} ${
                  compact ? (size === 'big' ? 'text-[13px]' : 'text-[11.5px]') : PCT_SIZE[size]
                }`}
              >
                {pctText(t.pct)}
              </span>
            )}
            {size !== 'tiny' && size !== 'xs' && sleeves.length > 0 && (
              <span aria-hidden="true" className="absolute right-2.5 top-[11px] flex gap-[3px]">
                {sleeves.map((h) => (
                  <i
                    key={h.index}
                    className="h-[7px] w-[7px] rounded-[2px] shadow-[0_0_0_1px_rgb(var(--canvas))]"
                    style={{ background: sleeveColor(h.index) }}
                  />
                ))}
              </span>
            )}
            {showSpark && (
              <span className="absolute bottom-3.5 left-3 right-3" aria-hidden="true">
                <Sparkline
                  values={spark}
                  width={Math.max(40, r.w - 28)}
                  height={60}
                  tone="neutral"
                />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
