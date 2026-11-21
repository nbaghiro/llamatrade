import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, G, Line, Path, Text as SvgText } from 'react-native-svg';

import { linePath, rangeOf, yFor } from '../charts/paths';
import { fonts, makeStyles, radius, useTheme } from '../theme';
import { Text } from '../ui';
import { pinIndex, type DatedCitation } from './citations';

const H = 96;
const PAD = 12;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = (ms: number) => {
  const d = new Date(ms);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
};

/** A session's equity with each dated citation pinned on its day (explain2 A). */
export function CitedCurve({
  title,
  times,
  values,
  citations,
  active,
  onPin,
}: {
  title: string;
  times: readonly number[];
  values: readonly number[];
  citations: readonly DatedCitation[];
  active?: number | null;
  onPin?: (n: number) => void;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const range = rangeOf(values);
  const pins = citations
    .map((ct) => ({ n: ct.n, i: pinIndex(times, ct.at) }))
    .filter((p) => p.i >= 0);
  const x = (i: number) => (values.length <= 1 ? 0 : (i / (values.length - 1)) * w);

  return (
    <View style={s.card}>
      <View style={s.head}>
        <Text variant="label" tone="fg3" style={s.kick}>{title.toUpperCase()}</Text>
        {pins.length ? null : <Text variant="caption" tone="fg3">No dated sources</Text>}
      </View>
      <View onLayout={onLayout} style={{ height: H }}>
        {w > 0 && range ? (
          <Svg width={w} height={H}>
            <Path d={linePath(values, w, H, PAD, range)} stroke={c.accent} strokeWidth={1.6} fill="none" />
            {pins.map((p) => {
              const px = Math.min(w - 10, Math.max(10, x(p.i)));
              const py = yFor(values[p.i], range, H, PAD);
              const on = active === p.n;
              return (
                <G key={p.n}>
                  <Line x1={px} x2={px} y1={py} y2={H} stroke={c.lineStrong} strokeDasharray="2 3" />
                  <Circle cx={px} cy={Math.max(10, py - 12)} r={9} fill={on ? c.accent : c.accentFill} onPress={onPin ? () => onPin(p.n) : undefined} />
                  <SvgText x={px} y={Math.max(10, py - 12) + 3.5} fontSize={10} fontFamily={fonts.monoMedium} fill={c.accentInk} textAnchor="middle">
                    {String(p.n)}
                  </SvgText>
                </G>
              );
            })}
          </Svg>
        ) : null}
      </View>
      {times.length > 1 ? (
        <View style={s.axis}>
          <Text variant="caption" tone="fg3">{day(times[0])}</Text>
          <Text variant="caption" tone="fg3">{day(times[Math.floor(times.length / 2)])}</Text>
          <Text variant="caption" tone="fg3">{day(times[times.length - 1])}</Text>
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  card: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line, borderRadius: radius.lg, padding: 14, gap: 8 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  kick: { letterSpacing: 0.8 },
  axis: { flexDirection: 'row', justifyContent: 'space-between' },
}));
