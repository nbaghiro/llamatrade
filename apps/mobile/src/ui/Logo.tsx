import { View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import { fonts, makeStyles, radius, useTheme } from '../theme';
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
export function LogoMark({ size = 22, bold = false, color }: { size?: number; bold?: boolean; color?: string }) {
  const { c } = useTheme();
  const ink = color ?? c.fg;
  const scale = bold ? 1.1 : 1;
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <Path
        d="M8 2v20M12.4 13v16.5M25.6 13v16.5M16.8 12.5v10M21.2 13v9"
        stroke={ink}
        strokeWidth={bold ? 1.4 : 1.1}
        strokeLinecap="round"
      />
      <Rect x={2 - (3.2 * scale - 3.2) / 2} y={7} width={3.2 * scale} height={4} rx={0.5} fill={c.accent} />
      {BODY.map(([x, y, w, h]) => (
        <Rect key={x} x={x - (w * scale - w) / 2} y={y} width={w * scale} height={h} rx={0.5} fill={ink} />
      ))}
    </Svg>
  );
}

/**
 * Copilot's mark, the Wick Asterisk: one candle whose wick splits into three strokes, with the
 * body in the accent at its centre.
 */
export function CopilotMark({ size = 22, bold = false, color }: { size?: number; bold?: boolean; color?: string }) {
  const { c } = useTheme();
  const w = bold ? 5.3 : 4.8;
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <Path
        d="M16 3.5V28.5M5.2 9.75L26.8 22.25M5.2 22.25L26.8 9.75"
        stroke={color ?? c.fg}
        strokeWidth={bold ? 1.9 : 1.7}
        strokeLinecap="round"
      />
      <Rect x={16 - w / 2} y={10} width={w} height={12} rx={0.6} fill={c.accent} />
    </Svg>
  );
}

/** The brand as in the web top bar: the 34pt Candlesticks mark with the caps wordmark. */
export function BrandLockup({ size = 34 }: { size?: number }) {
  const s = useStyles();
  return (
    <View style={s.lockup}>
      <LogoMark size={size} bold />
      <Text variant="label" style={s.word}>
        LLAMATRADE
      </Text>
    </View>
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
  lockup: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  word: { fontFamily: fonts.semibold, fontSize: 12, lineHeight: 14, letterSpacing: 1.9 },
  tile: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: t.c.panel,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
  },
}));
