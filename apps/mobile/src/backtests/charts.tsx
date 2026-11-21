import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, ClipPath, Defs, G, Line, LinearGradient, Path, Rect, Stop } from 'react-native-svg';

import { areaPath, linePath, rangeOf } from '../charts/paths';
import { makeStyles, useTheme } from '../theme';
import { Text } from '../ui';
import type { Lane } from './model';

export interface Band {
  /** Fractions of the width. */
  from: number;
  to: number;
  tone?: 'neutral' | 'loss';
}

interface CurveProps {
  values: readonly number[];
  /** Dashed comparison on the same scale. */
  benchmark?: readonly number[];
  height?: number;
  /** Shaded vertical stretches behind the lines. */
  bands?: readonly Band[];
  /** A vertical line at a fraction of the width, e.g. Now or where a run stopped. */
  marker?: { at: number; tone: 'fg' | 'risk' };
  /** Hatched region at the left, e.g. warm-up before the range. */
  shadeBefore?: number;
  /** Highlight from this fraction to the right edge, e.g. the chosen range. */
  selectFrom?: number;
  /** Draw on a log scale (values must be positive). */
  log?: boolean;
  /** The line stops at this fraction of the width, for a run still drawing in. */
  drawTo?: number;
  dot?: boolean;
}

const PAD = 4;

/** An equity curve in the accent with an optional dashed benchmark, bands and a marker; sizes to its container. */
export function Curve({ values, benchmark, height = 160, bands, marker, shadeBefore, selectFrom, log = false, drawTo = 1, dot = false }: CurveProps) {
  const { c, mode } = useTheme();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const tf = (s: readonly number[] | undefined) => (s && log ? s.map((v) => (v > 0 ? Math.log(v) : Number.NaN)) : s);
  const main = tf(values) ?? [];
  const bench = tf(benchmark);
  const range = rangeOf(main, bench);
  const lineW = Math.max(0, w * Math.max(0, Math.min(1, drawTo)));
  const lastY = range && main.length ? lastYOf(main, range, height) : null;
  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 && range ? (
        <Svg width={w} height={height}>
          <Defs>
            <LinearGradient id="curveFill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={c.accent} stopOpacity={mode === 'dark' ? 0.24 : 0.16} />
              <Stop offset="1" stopColor={c.accent} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          {selectFrom !== undefined ? <Rect x={w * selectFrom} y={0} width={w * (1 - selectFrom)} height={height} fill={c.accentSoft} /> : null}
          {shadeBefore !== undefined && shadeBefore > 0 ? (
            <>
              <ClipPath id="warmup">
                <Rect x={0} y={0} width={w * shadeBefore} height={height} />
              </ClipPath>
              <G clipPath="url(#warmup)">
                {Array.from({ length: Math.ceil((w * shadeBefore + height) / 6) }, (_, i) => (
                  <Line key={i} x1={i * 6} y1={0} x2={i * 6 - height} y2={height} stroke={c.lineStrong} strokeWidth={1} />
                ))}
              </G>
            </>
          ) : null}
          {(bands ?? []).map((b, i) => (
            <Rect
              key={i}
              x={w * b.from}
              y={0}
              width={Math.max(2, w * (b.to - b.from))}
              height={height}
              fill={b.tone === 'loss' ? c.loss : c.fg3}
              fillOpacity={b.tone === 'loss' ? 0.12 : 0.1}
            />
          ))}
          {bench && bench.length > 1 ? (
            <Path d={linePath(bench, w, height, PAD, range)} fill="none" stroke={c.fg3} strokeWidth={1.2} strokeDasharray="3 3" />
          ) : null}
          <Path d={areaPath(main, lineW, height, PAD, range)} fill="url(#curveFill)" />
          <Path d={linePath(main, lineW, height, PAD, range)} fill="none" stroke={c.accent} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
          {dot && lastY !== null ? (
            <>
              <Circle cx={lineW - PAD} cy={lastY} r={6} fill={c.accent} fillOpacity={0.2} />
              <Circle cx={lineW - PAD} cy={lastY} r={3} fill={c.accent} />
            </>
          ) : null}
          {marker ? (
            <Line x1={w * marker.at} x2={w * marker.at} y1={0} y2={height} stroke={marker.tone === 'risk' ? c.risk : c.fg} strokeWidth={1.2} />
          ) : null}
        </Svg>
      ) : null}
    </View>
  );
}

function lastYOf(values: readonly number[], range: { min: number; max: number }, h: number): number {
  const v = values[values.length - 1];
  const span = range.max - range.min;
  return span === 0 ? h / 2 : PAD + (h - PAD * 2) * (1 - (v - range.min) / span);
}

/** One row per symbol: rounded spans where it was held, on the same x axis as the curve above. */
export function Lanes({ lanes, marker }: { lanes: readonly Lane[]; marker?: { at: number; tone: 'fg' | 'risk' } }) {
  const s = useStyles();
  const { c } = useTheme();
  const [w, setW] = useState(0);
  if (!lanes.length) return null;
  return (
    <View style={s.lanes}>
      {lanes.map((lane) => (
        <View key={lane.symbol} style={s.lane}>
          <Text variant="numSmall" tone="fg3" style={s.laneSym}>{lane.symbol}</Text>
          <View style={s.track} onLayout={(e) => setW(Math.round(e.nativeEvent.layout.width))}>
            {w > 0 ? (
              <Svg width={w} height={12}>
                <Line x1={0} x2={w} y1={6} y2={6} stroke={c.line} strokeWidth={1} />
                {lane.spans.map((sp, i) => (
                  <Rect key={i} x={w * sp.from} y={1} width={Math.max(3, w * (sp.to - sp.from))} height={10} rx={3} fill={c.accent} fillOpacity={0.32} stroke={c.accent} strokeOpacity={0.5} strokeWidth={0.75} />
                ))}
                {marker ? <Line x1={w * marker.at} x2={w * marker.at} y1={0} y2={12} stroke={marker.tone === 'risk' ? c.risk : c.fg} strokeWidth={1.2} /> : null}
              </Svg>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

/** A labelled row of dots on the curve's x axis, e.g. the days a session rebalanced. */
export function MarkLane({ label, marks }: { label: string; marks: readonly number[] }) {
  const s = useStyles();
  const { c } = useTheme();
  const [w, setW] = useState(0);
  return (
    <View style={s.lane}>
      <Text variant="caption" tone="fg3" style={s.markLabel}>{label}</Text>
      <View style={s.track} onLayout={(e) => setW(Math.round(e.nativeEvent.layout.width))}>
        {w > 0 ? (
          <Svg width={w} height={12}>
            <Line x1={0} x2={w} y1={6} y2={6} stroke={c.lineStrong} strokeWidth={1} />
            {marks.map((m, i) => (
              <Circle key={i} cx={Math.min(w - 5, Math.max(5, w * m))} cy={6} r={4} fill={c.panel} stroke={c.accent} strokeWidth={1.2} />
            ))}
          </Svg>
        ) : null}
      </View>
    </View>
  );
}

/** "— Session  --- Backtest, same dates". */
export function LineKey({ main, dashed }: { main: string; dashed?: string }) {
  const s = useStyles();
  const { c } = useTheme();
  return (
    <View style={s.key}>
      <View style={s.keyItem}>
        <View style={[s.swatch, { backgroundColor: c.accent }]} />
        <Text variant="caption" tone="fg2">{main}</Text>
      </View>
      {dashed ? (
        <View style={s.keyItem}>
          <View style={[s.swatch, s.dashed, { borderColor: c.fg3 }]} />
          <Text variant="caption" tone="fg2">{dashed}</Text>
        </View>
      ) : null}
    </View>
  );
}

/** First, middle and last labels under a chart. */
export function AxisLabels({ labels }: { labels: readonly string[] }) {
  const s = useStyles();
  if (!labels.length) return null;
  return (
    <View style={s.axis}>
      {labels.map((l, i) => (
        <Text key={`${l}-${i}`} variant="numSmall" tone="fg3" style={s.axisText}>{l}</Text>
      ))}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  lanes: { gap: 4, marginTop: 6 },
  lane: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  laneSym: { width: 36, fontSize: 10.5 },
  markLabel: { width: 72 },
  track: { flex: 1, height: 12 },
  key: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  keyItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatch: { width: 14, height: 2, borderRadius: 1 },
  dashed: { height: 0, borderTopWidth: 1.5, borderStyle: 'dashed', backgroundColor: 'transparent' },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  axisText: { fontSize: 10.5, color: t.c.fg3 },
}));
