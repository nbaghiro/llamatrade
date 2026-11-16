import { Pressable, View, type StyleProp, type ViewStyle } from 'react-native';

import { makeStyles, radius } from '../theme';
import { Text } from './Text';

export interface Segment<K extends string = string> {
  key: K;
  label: string;
}

interface SegmentedProps<K extends string> {
  options: readonly Segment<K>[];
  value: K;
  onChange: (key: K) => void;
  disabledKeys?: readonly K[];
  /** Stretch segments to the full width instead of hugging their labels. */
  fill?: boolean;
  style?: StyleProp<ViewStyle>;
}

/** Segmented control: the selected segment is a raised panel inside a sunk track. */
export function Segmented<K extends string>({
  options,
  value,
  onChange,
  disabledKeys = [],
  fill = false,
  style,
}: SegmentedProps<K>) {
  const s = useStyles();
  return (
    <View accessibilityRole="tablist" style={[s.track, fill ? s.trackFill : null, style]}>
      {options.map((opt) => {
        const on = opt.key === value;
        const disabled = disabledKeys.includes(opt.key);
        return (
          <Pressable
            key={opt.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: on, disabled }}
            onPress={disabled || on ? undefined : () => onChange(opt.key)}
            disabled={disabled}
            style={[s.seg, fill ? s.segFill : null, on ? s.segOn : null, disabled ? s.segDisabled : null]}
          >
            <Text variant={on ? 'smallStrong' : 'small'} tone={on ? 'fg' : 'fg2'}>
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  track: {
    flexDirection: 'row',
    alignSelf: 'flex-start',
    padding: 2,
    gap: 2,
    borderRadius: radius.sm,
    backgroundColor: t.c.sunk,
    borderWidth: 1,
    borderColor: t.c.line,
  },
  trackFill: { alignSelf: 'stretch' },
  seg: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.xs, alignItems: 'center' },
  segFill: { flex: 1 },
  segOn: {
    backgroundColor: t.mode === 'dark' ? t.c.canvas : t.c.panel,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    paddingHorizontal: 11,
    paddingVertical: 5,
    ...t.shadow.sm,
  },
  segDisabled: { opacity: 0.4 },
}));
