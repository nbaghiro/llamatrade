import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, View, type StyleProp, type ViewStyle } from 'react-native';

import { makeStyles, radius, useTheme } from '../theme';
import { Text } from './Text';

export type ButtonVariant = 'primary' | 'secondary' | 'danger';
export type ButtonSize = 'md' | 'sm';

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}

/** Filled accent for the one main action; outlined panel for the rest. */
export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  disabled = false,
  style,
}: ButtonProps) {
  const { c } = useTheme();
  const s = useStyles();
  const inactive = disabled || loading;
  const primary = variant === 'primary';
  const fg = primary ? c.accentInk : variant === 'danger' ? c.loss : c.fg;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      onPress={inactive ? undefined : onPress}
      disabled={inactive}
      style={({ pressed }) => [
        s.base,
        size === 'sm' ? s.sm : s.md,
        primary ? s.primary : s.secondary,
        inactive ? s.inactive : null,
        pressed ? s.pressed : null,
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} size="small" /> : icon ? <View>{icon}</View> : null}
      <Text variant={size === 'sm' ? 'smallStrong' : 'subhead'} color={fg} style={size === 'md' ? s.label : null}>
        {label}
      </Text>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: radius.md,
    paddingHorizontal: 16,
  },
  md: { minHeight: 46 },
  sm: { minHeight: 34, paddingHorizontal: 12 },
  primary: { backgroundColor: t.c.accentFill },
  secondary: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.lineStrong },
  inactive: { opacity: 0.5 },
  pressed: { opacity: 0.8 },
  label: { fontSize: 15 },
}));
