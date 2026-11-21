/**
 * AnnotatedCurve props:
 *   series: readonly TimePoint[]        the main line ({ t: epoch ms, v }), drawn in the accent with a soft fill
 *   benchmark?: readonly TimePoint[]    dashed grey line on the same scale (e.g. SPY rebased to the series)
 *   step?: readonly TimePoint[]         dashed step line, e.g. money added; each value holds until the next
 *   pins?: readonly CurvePin[]          small labelled marks on dates: { t, label?, tone?: 'accent' | 'risk' | 'muted' }
 *   now?: number                        a vertical Now line with a dot on the series; tappable with onPressNow
 *   from?: number / until?: number      the x range; defaults to the data, and `until` past `now` shades the future
 *   height?: number                     plot height, default 150
 *   inset?: number                      left inset of the plot, so Lanes underneath line up (pass their labelWidth)
 *   xLabels?: boolean                   date labels under the plot, default true
 *   onPressNow?: () => void
 *   accessibilityLabel?: string
 */
import { useState } from 'react';
import { Pressable, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, Defs, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from 'react-native-svg';

import { fonts, useTheme } from '../theme';
import { Text } from '../ui/Text';
import {
  dateTicks,
  stepPath,
  timeAreaPath,
  timeLinePath,
  timeRangeOf,
  valueAt,
  valueRangeOf,
  xAt,
  yAt,
  type TimePoint,
  type TimeRange,
} from './scale';

export type { TimePoint, TimeRange } from './scale';

export interface CurvePin {
  t: number;
  label?: string;
  tone?: 'accent' | 'risk' | 'muted';
}

export interface AnnotatedCurveProps {
  series: readonly TimePoint[];
  benchmark?: readonly TimePoint[];
  step?: readonly TimePoint[];
  pins?: readonly CurvePin[];
  now?: number;
  from?: number;
  until?: number;
  height?: number;
  inset?: number;
  xLabels?: boolean;
  onPressNow?: () => void;
  accessibilityLabel?: string;
}

const PAD = 6;

/** The account or a session's curve with its events on the same dates. */
export function AnnotatedCurve({
  series,
  benchmark,
  step,
  pins,
  now,
  from,
  until,
  height = 150,
  inset = 0,
  xLabels = true,
  onPressNow,
  accessibilityLabel,
}: AnnotatedCurveProps) {
  const { c, mode } = useTheme();
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(Math.round(e.nativeEvent.layout.width));

  const data = timeRangeOf(series, benchmark, step);
  const range: TimeRange | null = data
    ? { from: from ?? data.from, until: Math.max(until ?? data.until, now ?? -Infinity) }
    : null;
  const inRange = (p: TimePoint) => range !== null && p.t >= range.from && p.t <= range.until;
  const values = valueRangeOf(series.filter(inRange), benchmark?.filter(inRange), step?.filter(inRange));
  const plotW = Math.max(0, width - inset);
  const ready = width > 0 && range !== null && values !== null && range.until > range.from;
  const opts = { left: inset, pad: PAD };
  const nowX = ready && now !== undefined ? xAt(now, range, plotW, inset) : null;
  const nowV = now !== undefined ? valueAt(series, now) : null;
  const nowY = ready && nowV !== null ? yAt(nowV, values, height, PAD) : null;
  const futureX = ready && now !== undefined && range.until > now ? nowX : null;
  const ticks = ready && xLabels ? dateTicks(range, 3) : [];
  const fillTop = mode === 'dark' ? 0.24 : 0.16;

  return (
    <View onLayout={onLayout} accessibilityLabel={accessibilityLabel}>
      {ready ? (
        <Svg width={width} height={height}>
          <Defs>
            <LinearGradient id="ac-fill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={c.accent} stopOpacity={fillTop} />
              <Stop offset="1" stopColor={c.accent} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          {futureX !== null ? (
            <Rect x={futureX} y={0} width={Math.max(0, width - futureX)} height={height} fill={c.sunk} opacity={mode === 'dark' ? 0.55 : 0.8} />
          ) : null}
          <Path d={timeAreaPath(series, range, values, plotW, height, opts)} fill="url(#ac-fill)" />
          {benchmark && benchmark.length > 1 ? (
            <Path
              d={timeLinePath(benchmark, range, values, plotW, height, opts)}
              fill="none"
              stroke={c.fg3}
              strokeWidth={1.2}
              strokeDasharray="3 3"
            />
          ) : null}
          {step && step.length ? (
            <Path
              d={stepPath(step, range, values, plotW, height, opts)}
              fill="none"
              stroke={c.fg2}
              strokeWidth={1.2}
              strokeDasharray="4 3"
            />
          ) : null}
          <Path
            d={timeLinePath(series, range, values, plotW, height, opts)}
            fill="none"
            stroke={c.accent}
            strokeWidth={1.8}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {(pins ?? []).map((p, i) => {
            if (p.t < range.from || p.t > range.until) return null;
            const x = xAt(p.t, range, plotW, inset);
            const color = p.tone === 'risk' ? c.risk : p.tone === 'muted' ? c.fg3 : c.accent;
            return (
              <PinMark key={`${p.t}-${i}`} x={x} height={height} color={color} label={p.label} grid={c.lineStrong} />
            );
          })}
          {nowX !== null ? (
            <Line x1={nowX} x2={nowX} y1={0} y2={height} stroke={c.fg3} strokeWidth={1} strokeDasharray="2 3" />
          ) : null}
          {nowX !== null && nowY !== null ? (
            <>
              <Circle cx={nowX} cy={nowY} r={7} fill={c.accent} opacity={0.18} />
              <Circle cx={nowX} cy={nowY} r={3.5} fill={c.accent} stroke={c.canvas} strokeWidth={1.5} />
            </>
          ) : null}
        </Svg>
      ) : (
        <View style={{ height }} />
      )}
      {nowX !== null && nowY !== null && onPressNow ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Open today"
          onPress={onPressNow}
          hitSlop={12}
          style={{ position: 'absolute', left: nowX - 16, top: nowY - 16, width: 32, height: 32 }}
        />
      ) : null}
      {ticks.length ? (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, paddingLeft: inset }}>
          {ticks.map((t, i) => (
            <Text key={`${t.label}-${i}`} variant="numSmall" tone="fg3" style={{ fontSize: 10.5 }}>
              {i === ticks.length - 1 && now !== undefined && range && Math.abs(range.until - now) < 36e5 ? 'Now' : t.label}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function PinMark({ x, height, color, label, grid }: { x: number; height: number; color: string; label?: string; grid: string }) {
  return (
    <>
      <Line x1={x} x2={x} y1={label ? 14 : 0} y2={height} stroke={grid} strokeWidth={1} strokeDasharray="1 3" />
      <Path d={`M${x - 3.5},${height - 1} L${x},${height - 6} L${x + 3.5},${height - 1} Z`} fill={color} />
      {label ? (
        <SvgText x={x} y={10} fill={color} fontSize={9.5} fontFamily={fonts.mono} textAnchor="middle">
          {label}
        </SvgText>
      ) : null}
    </>
  );
}
