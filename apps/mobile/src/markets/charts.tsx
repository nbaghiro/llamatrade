import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, G, Line, Path, Rect, Text as SvgText } from 'react-native-svg';

import { linePath } from '../charts/paths';
import { fonts, useTheme } from '../theme';
import type { Candle } from '@llamatrade/core/stores/markets';
import { placeFills, priceRange, type FillMark } from './model';

/** A small line for a row: the last weeks of daily closes in the accent. */
export function Sparkline({ values, width = 78, height = 28 }: { values: readonly number[]; width?: number; height?: number }) {
  const { c } = useTheme();
  const d = linePath(values, width, height, 2);
  if (!d) return <View style={{ width, height }} />;
  return (
    <Svg width={width} height={height}>
      <Path d={d} fill="none" stroke={c.accent} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}

export interface CostLine {
  price: number;
  /** Solid for live, dashed for paper. */
  mode: 'live' | 'paper';
  label: string;
}

const AXIS_W = 40;

/**
 * Candles with the price axis on the right, each fill as a B or S badge at its price (filled for
 * live, outlined for paper) and each holder's average cost as a line.
 */
export function CandleChart({
  candles,
  fills = [],
  fillMode,
  costs = [],
  height = 230,
}: {
  candles: readonly Candle[];
  fills?: readonly FillMark[];
  /** Paper or live for each fill's session. */
  fillMode?: (sessionId: string) => 'live' | 'paper';
  costs?: readonly CostLine[];
  height?: number;
}) {
  const { c } = useTheme();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const placed = placeFills(fills, candles);
  const range = priceRange(candles, [...placed.map((p) => p.price), ...costs.map((k) => k.price)]);
  const plotW = Math.max(0, w - AXIS_W);
  const pad = 10;
  const y = (v: number) => (range ? pad + (height - pad * 2) * (1 - (v - range.min) / (range.max - range.min || 1)) : height / 2);
  const n = candles.length;
  const step = n > 0 ? plotW / n : 0;
  const bodyW = Math.max(1, Math.min(9, step * 0.62));
  const ticks = range ? [0, 1, 2, 3].map((i) => range.max - ((range.max - range.min) * (i + 0.5)) / 4) : [];

  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 && range ? (
        <Svg width={w} height={height}>
          {ticks.map((v) => (
            <G key={v}>
              <Line x1={0} x2={plotW} y1={y(v)} y2={y(v)} stroke={c.grid} strokeWidth={1} strokeDasharray="1 4" />
              <SvgText x={w - 2} y={y(v) + 3.5} textAnchor="end" fill={c.fg3} fontSize={10.5} fontFamily={fonts.mono}>
                {v >= 1000 ? v.toFixed(0) : v >= 100 ? v.toFixed(1) : v.toFixed(2)}
              </SvgText>
            </G>
          ))}
          {costs.map((k) => (
            <Line
              key={`${k.label}-${k.price}`}
              x1={0}
              x2={plotW}
              y1={y(k.price)}
              y2={y(k.price)}
              stroke={c.accent}
              strokeOpacity={0.75}
              strokeWidth={1}
              strokeDasharray={k.mode === 'paper' ? '4 3' : undefined}
            />
          ))}
          {candles.map((k, i) => {
            const cx = step * i + step / 2;
            const up = k.close >= k.open;
            const top = y(Math.max(k.open, k.close));
            const bottom = y(Math.min(k.open, k.close));
            return (
              <G key={k.time}>
                <Line x1={cx} x2={cx} y1={y(k.high)} y2={y(k.low)} stroke={c.fg2} strokeWidth={1} />
                <Rect
                  x={cx - bodyW / 2}
                  y={top}
                  width={bodyW}
                  height={Math.max(1, bottom - top)}
                  fill={up ? c.panel : c.fg2}
                  stroke={c.fg2}
                  strokeWidth={1}
                />
              </G>
            );
          })}
          {placed.map((p, i) => {
            const cx = step * p.index + step / 2;
            const live = fillMode?.(p.sessionId) === 'live';
            return (
              <G key={`${p.at}-${i}`}>
                <Circle cx={cx} cy={y(p.price)} r={8} fill={live ? c.fg : p.side === 'buy' ? c.accentFill : c.panel} stroke={live ? c.fg : c.accent} strokeWidth={1.4} />
                <SvgText
                  x={cx}
                  y={y(p.price) + 3.5}
                  textAnchor="middle"
                  fill={live ? c.canvas : p.side === 'buy' ? c.accentInk : c.accent}
                  fontSize={9.5}
                  fontFamily={fonts.monoSemibold}
                >
                  {p.side === 'buy' ? 'B' : 'S'}
                </SvgText>
              </G>
            );
          })}
        </Svg>
      ) : null}
    </View>
  );
}
