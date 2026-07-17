import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { fonts, palette } from '../theme';

export interface Segment {
  key: string;
  label: string;
}

interface SegmentedToggleProps {
  options: Segment[];
  value: string;
  onChange: (key: string) => void;
  disabledKeys?: string[];
  style?: StyleProp<ViewStyle>;
}

/** Monolith segmented control (paper/live, monthly/yearly): ink fill marks the active segment. */
export function SegmentedToggle({
  options,
  value,
  onChange,
  disabledKeys = [],
  style,
}: SegmentedToggleProps) {
  return (
    <View style={[styles.row, style]}>
      {options.map((opt, i) => {
        const active = opt.key === value;
        const isDisabled = disabledKeys.includes(opt.key);
        return (
          <Pressable
            key={opt.key}
            onPress={isDisabled || active ? undefined : () => onChange(opt.key)}
            disabled={isDisabled}
            style={[
              styles.seg,
              i > 0 ? styles.segJoin : null,
              { backgroundColor: active ? palette.ink : palette.paper, opacity: isDisabled ? 0.4 : 1 },
            ]}
          >
            <Text style={[styles.label, { color: active ? palette.bone : palette.ink }]}>
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row' },
  seg: {
    flex: 1,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: palette.ink,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  segJoin: { marginLeft: -2 }, // collapse the shared border between segments
  label: {
    fontFamily: fonts.mono,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
});
