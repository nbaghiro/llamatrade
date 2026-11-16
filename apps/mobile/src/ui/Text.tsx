import type { ReactNode } from 'react';
import { Text as RNText, type StyleProp, type TextStyle } from 'react-native';

import { fonts, useTheme, type Colors } from '../theme';

const VARIANTS = {
  title: { fontFamily: fonts.semibold, fontSize: 28, lineHeight: 32, letterSpacing: -0.6 },
  heading: { fontFamily: fonts.semibold, fontSize: 20, lineHeight: 25, letterSpacing: -0.3 },
  subhead: { fontFamily: fonts.semibold, fontSize: 16, lineHeight: 21, letterSpacing: -0.1 },
  body: { fontFamily: fonts.sans, fontSize: 15, lineHeight: 21 },
  bodyStrong: { fontFamily: fonts.medium, fontSize: 15, lineHeight: 21 },
  small: { fontFamily: fonts.sans, fontSize: 13.5, lineHeight: 19 },
  smallStrong: { fontFamily: fonts.medium, fontSize: 13.5, lineHeight: 19 },
  label: { fontFamily: fonts.medium, fontSize: 12, lineHeight: 16 },
  caption: { fontFamily: fonts.sans, fontSize: 11.5, lineHeight: 15 },
  num: { fontFamily: fonts.mono, fontSize: 14, lineHeight: 19, fontVariant: ['tabular-nums'] },
  numStrong: { fontFamily: fonts.monoMedium, fontSize: 14, lineHeight: 19, fontVariant: ['tabular-nums'] },
  numSmall: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 16, fontVariant: ['tabular-nums'] },
  numLarge: { fontFamily: fonts.monoMedium, fontSize: 20, lineHeight: 25, letterSpacing: -0.4, fontVariant: ['tabular-nums'] },
  hero: { fontFamily: fonts.monoSemibold, fontSize: 34, lineHeight: 40, letterSpacing: -1.2, fontVariant: ['tabular-nums'] },
} as const satisfies Record<string, TextStyle>;

export type TextVariant = keyof typeof VARIANTS;
export type TextTone = 'fg' | 'fg2' | 'fg3' | 'accent' | 'accentInk' | 'gain' | 'loss' | 'risk';

const TONE: Record<TextTone, Exclude<keyof Colors, 'chart'>> = {
  fg: 'fg',
  fg2: 'fg2',
  fg3: 'fg3',
  accent: 'accent',
  accentInk: 'accentInk',
  gain: 'gain',
  loss: 'loss',
  risk: 'risk',
};

interface TextProps {
  children: ReactNode;
  variant?: TextVariant;
  tone?: TextTone;
  /** Overrides `tone`. */
  color?: string;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
  onPress?: () => void;
  selectable?: boolean;
}

/** All app text: a type role from the scale plus a colour role from the theme. */
export function Text({
  children,
  variant = 'body',
  tone = 'fg',
  color,
  style,
  numberOfLines,
  onPress,
  selectable,
}: TextProps) {
  const { c } = useTheme();
  return (
    <RNText
      numberOfLines={numberOfLines}
      onPress={onPress}
      selectable={selectable}
      style={[VARIANTS[variant], { color: color ?? c[TONE[tone]] }, style]}
    >
      {children}
    </RNText>
  );
}

/** Profit-and-loss tone by sign; flat values stay neutral. */
export function pnlTone(value: number): TextTone {
  if (value > 0) return 'gain';
  if (value < 0) return 'loss';
  return 'fg';
}
