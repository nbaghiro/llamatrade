import { View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import { makeStyles, radius, useTheme } from '../theme';
import { Text } from './Text';

const BODY: ReadonlyArray<readonly [number, number, number, number]> = [
  [6.4, 4.5, 3.2, 14],
  [10.8, 14.5, 3.2, 10],
  [15.2, 14.5, 3.2, 6],
  [19.6, 15, 3.2, 5.5],
  [24, 14.5, 3.2, 10],
  [28.4, 13, 2, 4.5],
];

/** The Candlesticks mark: a llama drawn as a run of candles, the first one in the accent. */
export function LogoMark({ size = 22 }: { size?: number }) {
  const { c } = useTheme();
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <Path
        d="M8 2v20M12.4 13v16.5M25.6 13v16.5M16.8 12.5v10M21.2 13v9"
        stroke={c.fg}
        strokeWidth={1.1}
        strokeLinecap="round"
      />
      <Rect x={2} y={7} width={3.2} height={4} rx={0.5} fill={c.accent} />
      {BODY.map(([x, y, w, h]) => (
        <Rect key={x} x={x} y={y} width={w} height={h} rx={0.5} fill={c.fg} />
      ))}
    </Svg>
  );
}

/** Mark in a rounded tile, with the wordmark beside it when `showText`. */
export function Logo({ size = 40, showText = false }: { size?: number; showText?: boolean }) {
  const s = useStyles();
  return (
    <View style={s.row}>
      <View style={[s.tile, { width: size, height: size }]}>
        <LogoMark size={Math.round(size * 0.72)} />
      </View>
      {showText ? (
        <Text variant="subhead" style={{ fontSize: Math.max(15, Math.round(size * 0.45)) }}>
          LlamaTrade
        </Text>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  tile: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: t.c.panel,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
  },
}));
