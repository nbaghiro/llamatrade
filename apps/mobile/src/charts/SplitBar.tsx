/**
 * SplitBar props:
 *   segments: readonly SplitSegment[]   laid end to end by `value`; zero and negative values are skipped
 *     SplitSegment { key: string; value: number; look: 'solid' | 'hatched' | 'muted'; color?: string; label?: string }
 *     solid is ink (live money), hatched is the accent with diagonal stripes (paper), muted is a quiet grey
 *   height?: number                     default 10
 *   selected?: string | null            the key drawn at full strength while the others dim
 *   onPress?: (key: string) => void     tapping a segment; omit for a static bar
 */
import { useId, useState } from 'react';
import { Pressable, View, type LayoutChangeEvent } from 'react-native';
import Svg, { ClipPath, Defs, G, Path, Rect } from 'react-native-svg';

import { useTheme } from '../theme';
import { splitWidths } from './scale';

export interface SplitSegment {
  key: string;
  value: number;
  look: 'solid' | 'hatched' | 'muted';
  color?: string;
  label?: string;
}

export interface SplitBarProps {
  segments: readonly SplitSegment[];
  height?: number;
  selected?: string | null;
  onPress?: (key: string) => void;
}

const GAP = 3;
const HATCH = 5;

/** Diagonal strokes across a segment, clipped by the caller. */
function hatchPath(x: number, w: number, h: number): string {
  let d = '';
  for (let k = x - h; k < x + w; k += HATCH) d += `M${k.toFixed(1)},${h} L${(k + h).toFixed(1)},0 `;
  return d;
}

/** A bar split by share, e.g. live money against paper. */
export function SplitBar({ segments, height = 10, selected = null, onPress }: SplitBarProps) {
  const { c, mode } = useTheme();
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(Math.round(e.nativeEvent.layout.width));
  const widths = splitWidths(
    segments.map((s) => s.value),
    width,
    GAP,
  );
  let x = 0;
  const placed = segments.map((s, i) => {
    const w = widths[i];
    const at = x;
    if (w > 0) x += w + GAP;
    return { s, x: at, w };
  });
  const r = Math.min(3, height / 2);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  return (
    <View onLayout={onLayout} style={{ height }}>
      {width > 0 ? (
        <Svg width={width} height={height}>
          <Defs>
            {placed.map(({ s, x: px, w }) =>
              s.look === 'hatched' && w > 0 ? (
                <ClipPath key={s.key} id={`hatch-${uid}-${s.key}`}>
                  <Rect x={px} y={0} width={w} height={height} rx={r} />
                </ClipPath>
              ) : null,
            )}
          </Defs>
          {placed.map(({ s, x: px, w }) => {
            if (w <= 0) return null;
            const dim = selected !== null && selected !== s.key;
            const opacity = dim ? 0.35 : 1;
            if (s.look === 'hatched') {
              const color = s.color ?? c.accent;
              return (
                <G key={s.key} opacity={opacity}>
                  <G clipPath={`url(#hatch-${uid}-${s.key})`}>
                    <Rect x={px} y={0} width={w} height={height} fill={color} opacity={0.14} />
                    <Path d={hatchPath(px, w, height)} stroke={color} strokeWidth={1.6} />
                  </G>
                  <Rect x={px + 0.5} y={0.5} width={Math.max(0, w - 1)} height={height - 1} rx={r} fill="none" stroke={color} strokeWidth={1} />
                </G>
              );
            }
            const fill = s.color ?? (s.look === 'solid' ? c.fg : mode === 'dark' ? c.lineStrong : c.line);
            return <Rect key={s.key} x={px} y={0} width={w} height={height} rx={r} fill={fill} opacity={opacity} />;
          })}
        </Svg>
      ) : null}
      {onPress && width > 0
        ? placed.map(({ s, x: px, w }) =>
            w > 0 ? (
              <Pressable
                key={s.key}
                accessibilityRole="button"
                accessibilityLabel={s.label ?? s.key}
                accessibilityState={{ selected: selected === s.key }}
                onPress={() => onPress(s.key)}
                hitSlop={{ top: 14, bottom: 14 }}
                style={{ position: 'absolute', left: px, top: 0, width: w, height }}
              />
            ) : null,
          )
        : null}
    </View>
  );
}
