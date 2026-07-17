import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { fonts, palette } from '../theme';

type ButtonVariant = 'primary' | 'secondary' | 'danger';

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}

const VARIANT: Record<ButtonVariant, { bg: string; fg: string; border: string; shadow: boolean }> = {
  primary: { bg: palette.orange[500], fg: palette.ink, border: palette.ink, shadow: true },
  secondary: { bg: palette.paper, fg: palette.ink, border: palette.ink, shadow: false },
  danger: { bg: palette.paper, fg: palette.red[500], border: palette.red[500], shadow: false },
};

/** Monolith button: hard border, offset shadow on primary, mono uppercase label. */
export function Button({
  label,
  onPress,
  variant = 'primary',
  loading = false,
  disabled = false,
  style,
}: ButtonProps) {
  const v = VARIANT[variant];
  const inactive = disabled || loading;

  return (
    <View style={[styles.wrap, style]}>
      {v.shadow && !inactive ? <View style={styles.shadow} pointerEvents="none" /> : null}
      <Pressable
        onPress={inactive ? undefined : onPress}
        disabled={inactive}
        style={({ pressed }) => [
          styles.base,
          { backgroundColor: v.bg, borderColor: v.border, opacity: inactive ? 0.5 : 1 },
          pressed && v.shadow ? { transform: [{ translateX: 2 }, { translateY: 2 }] } : null,
        ]}
      >
        {loading ? (
          <ActivityIndicator color={v.fg} size="small" />
        ) : (
          <Text style={[styles.label, { color: v.fg }]}>{label}</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'relative' },
  shadow: { position: 'absolute', left: 4, top: 4, right: -4, bottom: -4, backgroundColor: palette.ink },
  base: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  label: {
    fontFamily: fonts.mono,
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
});
