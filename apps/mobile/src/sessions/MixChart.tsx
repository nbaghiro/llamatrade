import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Line, Path } from 'react-native-svg';

import { useTheme } from '../theme';
import type { Mix } from './model';

/**
 * Stacked daily weights: the first symbol at the bottom in the accent, each next one lighter,
 * cash on top in grey. A vertical line marks the selected day.
 */
export function MixChart({ mix, selected, height = 200 }: { mix: Mix; selected?: number | null; height?: number }) {
  const { c, mode } = useTheme();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const days = mix.days;
  const n = days.length;
  const x = (i: number) => (n > 1 ? (w * i) / (n - 1) : w / 2);
  const y = (f: number) => height * (1 - f);

  const bands: string[] = [];
  if (n > 1 && w > 0) {
    const layers = mix.symbols.length + 1;
    for (let k = 0; k < layers; k++) {
      const lower = days.map((d) => d.weights.slice(0, k).reduce((a, b) => a + b, 0));
      const upper = days.map((d, i) => lower[i] + (k < mix.symbols.length ? d.weights[k] : d.cash));
      const top = upper.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(Math.min(1, v)).toFixed(1)}`).join(' ');
      let bottom = '';
      for (let i = n - 1; i >= 0; i--) bottom += ` L${x(i).toFixed(1)},${y(Math.max(0, lower[i])).toFixed(1)}`;
      bands.push(`${top} ${bottom} Z`);
    }
  }
  const opacity = (k: number) => (mode === 'dark' ? [0.75, 0.45, 0.28, 0.18, 0.12] : [0.7, 0.42, 0.26, 0.16, 0.1])[Math.min(k, 4)];
  const selIdx = selected == null ? -1 : days.findIndex((d) => new Date(d.t).toDateString() === new Date(selected).toDateString());

  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 && n > 1 ? (
        <Svg width={w} height={height}>
          {bands.map((d, k) =>
            k < mix.symbols.length ? (
              <Path key={k} d={d} fill={c.accent} fillOpacity={opacity(k)} />
            ) : (
              <Path key={k} d={d} fill={c.fg3} fillOpacity={mode === 'dark' ? 0.18 : 0.14} />
            ),
          )}
          {selIdx >= 0 ? <Line x1={x(selIdx)} x2={x(selIdx)} y1={0} y2={height} stroke={c.fg} strokeWidth={1.25} /> : null}
        </Svg>
      ) : null}
    </View>
  );
}
