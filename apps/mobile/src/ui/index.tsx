import type { ReactNode } from 'react';
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

import { fonts, palette } from '../theme';

/* ---------------------------------------------------------------- Text ---- */

interface TextProps {
  children: ReactNode;
  size?: number;
  color?: string;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
}

export function Display({ children, size = 22, color = palette.ink, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[{ fontFamily: fonts.display, fontSize: size, color, textTransform: 'uppercase' }, style]}>
      {children}
    </Text>
  );
}

export function Body({ children, size = 14, color = palette.ink, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[{ fontFamily: fonts.sans, fontSize: size, color }, style]}>
      {children}
    </Text>
  );
}

export function Mono({ children, size = 12, color = palette.ink, style, numberOfLines }: TextProps) {
  return (
    <Text numberOfLines={numberOfLines} style={[{ fontFamily: fonts.mono, fontSize: size, color }, style]}>
      {children}
    </Text>
  );
}

export function Label({ children, color = palette.gray[500], style, numberOfLines }: Omit<TextProps, 'size'>) {
  return (
    <Text
      numberOfLines={numberOfLines}
      style={[
        { fontFamily: fonts.mono, fontSize: 10, color, letterSpacing: 0.8, textTransform: 'uppercase' },
        style,
      ]}
    >
      {children}
    </Text>
  );
}

/* ---------------------------------------------------------------- Card ---- */

export function Card({
  children,
  style,
  shadow = false,
  ink = false,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  shadow?: boolean;
  ink?: boolean;
}) {
  return (
    <View style={styles.cardWrap}>
      {shadow ? <View style={styles.cardShadow} pointerEvents="none" /> : null}
      <View
        style={[
          { backgroundColor: ink ? palette.ink : palette.paper, borderWidth: 2, borderColor: palette.ink, padding: 12 },
          style,
        ]}
      >
        {children}
      </View>
    </View>
  );
}

/* --------------------------------------------------------------- Badge ---- */

type BadgeVariant = 'gray' | 'orange' | 'ink' | 'green' | 'red' | 'blue';

const BADGE: Record<BadgeVariant, { bg: string; fg: string }> = {
  gray: { bg: palette.paper, fg: palette.ink },
  orange: { bg: palette.orange[500], fg: palette.ink },
  ink: { bg: palette.ink, fg: palette.bone },
  green: { bg: palette.green[500], fg: palette.bone },
  red: { bg: palette.red[500], fg: palette.bone },
  blue: { bg: palette.blue[500], fg: palette.bone },
};

export function Badge({ label, variant = 'gray' }: { label: string; variant?: BadgeVariant }) {
  const c = BADGE[variant];
  return (
    <View style={{ backgroundColor: c.bg, borderWidth: 1, borderColor: palette.ink, paddingHorizontal: 7, paddingVertical: 2 }}>
      <Text style={{ fontFamily: fonts.mono, fontSize: 10, fontWeight: '700', color: c.fg, letterSpacing: 0.4, textTransform: 'uppercase' }}>
        {label}
      </Text>
    </View>
  );
}

/* ------------------------------------------------------------- KpiTile ---- */

export function KpiTile({ value, label, tone }: { value: string; label: string; tone?: 'up' | 'down' }) {
  const color = tone === 'up' ? palette.green[500] : tone === 'down' ? palette.red[500] : palette.ink;
  return (
    <View style={{ flex: 1, backgroundColor: palette.paper, borderWidth: 2, borderColor: palette.ink, paddingHorizontal: 10, paddingVertical: 9 }}>
      <Display size={18} color={color}>
        {value}
      </Display>
      <Label style={{ marginTop: 5 }}>{label}</Label>
    </View>
  );
}

const styles = StyleSheet.create({
  cardWrap: { position: 'relative' },
  cardShadow: {
    position: 'absolute',
    left: 4,
    top: 4,
    right: -4,
    bottom: -4,
    backgroundColor: palette.ink,
  },
});
