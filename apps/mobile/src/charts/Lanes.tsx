/**
 * Lanes props:
 *   lanes: readonly Lane[]              one row each, on the same x axis as an AnnotatedCurve above
 *     Lane { key; label (short, e.g. "AW"); start?: t; end?: t; tone?: 'accent' | 'ink' | 'muted' | 'risk';
 *            dashed?: boolean (paper, or planned); markers: LaneMarker[] }
 *     LaneMarker { t; kind: 'fill' | 'planned' | 'stop' | 'start' | 'event'; count?: number; tone?; id?: string }
 *       fill: solid dot (a number inside when count > 1); planned: hollow dot; stop: square; start: diamond
 *   from: number / until: number         the shared x range (epoch ms)
 *   now?: number                         a dotted Now line through every lane
 *   labelWidth?: number                  width of the label column, default 28; pass it as the curve's `inset`
 *   rowHeight?: number                   default 20
 *   onPressMarker?: (lane: Lane, marker: LaneMarker) => void
 *   onPressLane?: (lane: Lane) => void   tapping the label
 */
import { Fragment, useState } from 'react';
import { Pressable, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, Line, Rect, Text as SvgText } from 'react-native-svg';

import { fonts, useTheme } from '../theme';
import { xAt, type TimeRange } from './scale';

export type LaneTone = 'accent' | 'ink' | 'muted' | 'risk';

export interface LaneMarker {
  t: number;
  kind: 'fill' | 'planned' | 'stop' | 'start' | 'event';
  count?: number;
  tone?: LaneTone;
  id?: string;
}

export interface Lane {
  key: string;
  label: string;
  start?: number;
  end?: number;
  tone?: LaneTone;
  dashed?: boolean;
  markers: readonly LaneMarker[];
}

export interface LanesProps {
  lanes: readonly Lane[];
  from: number;
  until: number;
  now?: number;
  labelWidth?: number;
  rowHeight?: number;
  onPressMarker?: (lane: Lane, marker: LaneMarker) => void;
  onPressLane?: (lane: Lane) => void;
}

/** One row per session, symbol or version, with markers and stretches on a shared time axis. */
export function Lanes({ lanes, from, until, now, labelWidth = 28, rowHeight = 20, onPressMarker, onPressLane }: LanesProps) {
  const { c } = useTheme();
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(Math.round(e.nativeEvent.layout.width));
  const range: TimeRange = { from, until };
  const plotW = Math.max(0, width - labelWidth - 6);
  const left = labelWidth;
  const height = lanes.length * rowHeight;
  const colorOf = (tone: LaneTone | undefined) =>
    tone === 'risk' ? c.risk : tone === 'muted' ? c.fg3 : tone === 'ink' ? c.fg : c.accent;
  const nowX = now !== undefined && until > from ? xAt(now, range, plotW, left) : null;

  return (
    <View onLayout={onLayout} style={{ height }}>
      {width > 0 && until > from ? (
        <Svg width={width} height={height}>
          {lanes.map((lane, i) => {
            const y = i * rowHeight + rowHeight / 2;
            const color = colorOf(lane.tone);
            const x0 = xAt(lane.start ?? from, range, plotW, left);
            const x1 = xAt(lane.end ?? until, range, plotW, left);
            return (
              <Fragment key={lane.key}>
                <Line x1={left} x2={left + plotW} y1={y} y2={y} stroke={c.line} strokeWidth={1} />
                {x1 > x0 ? (
                  <Line
                    x1={x0}
                    x2={x1}
                    y1={y}
                    y2={y}
                    stroke={color}
                    strokeOpacity={lane.tone === 'muted' ? 0.7 : 0.85}
                    strokeWidth={lane.tone === 'risk' ? 2.5 : 1.5}
                    strokeDasharray={lane.dashed ? '3 3' : undefined}
                  />
                ) : null}
                <SvgText x={0} y={y + 3.5} fill={lane.tone === 'risk' ? c.risk : c.fg3} fontSize={10} fontFamily={fonts.mono}>
                  {lane.label}
                </SvgText>
                {lane.markers.map((m, j) => {
                  if (m.t < from || m.t > until) return null;
                  const x = xAt(m.t, range, plotW, left);
                  const mc = colorOf(m.tone ?? lane.tone);
                  const key = `${lane.key}-${m.id ?? j}`;
                  if (m.kind === 'stop') return <Rect key={key} x={x - 4} y={y - 4} width={8} height={8} rx={1.5} fill={c.fg3} />;
                  if (m.kind === 'start')
                    return <Rect key={key} x={x - 3.5} y={y - 3.5} width={7} height={7} fill={mc} transform={`rotate(45 ${x} ${y})`} />;
                  if (m.kind === 'planned')
                    return <Circle key={key} cx={x} cy={y} r={4} fill={c.panel} stroke={mc} strokeWidth={1.4} strokeDasharray="2 1.5" />;
                  const counted = (m.count ?? 1) > 1;
                  return (
                    <Fragment key={key}>
                      <Circle cx={x} cy={y} r={counted ? 6.5 : 4} fill={mc} stroke={c.panel} strokeWidth={1.2} />
                      {counted ? (
                        <SvgText x={x} y={y + 3} fill={c.panel} fontSize={8.5} fontFamily={fonts.monoMedium} textAnchor="middle">
                          {String(Math.min(m.count ?? 0, 99))}
                        </SvgText>
                      ) : null}
                    </Fragment>
                  );
                })}
              </Fragment>
            );
          })}
          {nowX !== null ? <Line x1={nowX} x2={nowX} y1={0} y2={height} stroke={c.fg3} strokeWidth={1} strokeDasharray="2 3" /> : null}
        </Svg>
      ) : null}
      {width > 0 && onPressLane
        ? lanes.map((lane, i) => (
            <Pressable
              key={`label-${lane.key}`}
              accessibilityRole="button"
              accessibilityLabel={lane.label}
              onPress={() => onPressLane(lane)}
              style={{ position: 'absolute', left: 0, top: i * rowHeight, width: labelWidth, height: rowHeight }}
            />
          ))
        : null}
      {width > 0 && onPressMarker
        ? lanes.flatMap((lane, i) =>
            lane.markers
              .filter((m) => m.t >= from && m.t <= until && m.kind !== 'stop')
              .map((m, j) => {
                const x = xAt(m.t, range, plotW, left);
                return (
                  <Pressable
                    key={`hit-${lane.key}-${m.id ?? j}`}
                    accessibilityRole="button"
                    accessibilityLabel={`${lane.label} ${m.kind}`}
                    onPress={() => onPressMarker(lane, m)}
                    hitSlop={6}
                    style={{ position: 'absolute', left: x - 11, top: i * rowHeight, width: 22, height: rowHeight }}
                  />
                );
              }),
          )
        : null}
    </View>
  );
}
