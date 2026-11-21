import type { ReactNode } from 'react';
import { ActivityIndicator, Modal, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { makeStyles, radius, useTheme } from '../theme';
import { Text } from '../ui';

/** A bottom sheet over a dimmed screen; tapping outside closes it. */
export function Sheet({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  const s = useStyles();
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable accessibilityLabel="Close" style={s.scrim} onPress={onClose} />
      <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 16) + 8 }]}>
        <View style={s.grab} />
        {children}
      </View>
    </Modal>
  );
}

/** The one main action on a screen: an ink pill. */
export function InkButton({
  label,
  onPress,
  disabled = false,
  loading = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive }}
      onPress={inactive ? undefined : onPress}
      style={({ pressed }) => [s.ink, { backgroundColor: c.fg }, inactive ? { opacity: 0.4 } : null, pressed ? { opacity: 0.8 } : null]}
    >
      {loading ? <ActivityIndicator color={c.canvas} /> : <Text variant="bodyStrong" color={c.canvas}>{label}</Text>}
    </Pressable>
  );
}

/** A quiet outlined pill for the second choice. */
export function QuietButton({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [s.ink, s.quiet, { borderColor: c.lineStrong }, disabled ? { opacity: 0.4 } : null, pressed ? { opacity: 0.7 } : null]}
    >
      <Text variant="bodyStrong">{label}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  scrim: { flex: 1, backgroundColor: t.c.scrim },
  sheet: {
    backgroundColor: t.c.panel,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    paddingHorizontal: 20,
    paddingTop: 8,
    gap: 14,
    ...t.shadow.lg,
  },
  grab: { alignSelf: 'center', width: 36, height: 4, borderRadius: 2, backgroundColor: t.c.lineStrong, marginBottom: 4 },
  ink: { height: 50, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 20 },
  quiet: { borderWidth: 1, backgroundColor: 'transparent' },
}));
