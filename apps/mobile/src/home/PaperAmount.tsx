import type { StyleProp, TextStyle } from 'react-native';

import { useTheme } from '../theme';
import { Text, type TextTone, type TextVariant } from '../ui/Text';

/**
 * Money text marked by account (mode2 B): paper amounts carry a dashed underline, live and
 * mixed totals stay plain. Use it for any figure that belongs to one paper record.
 */
export function PaperAmount({
  children,
  paper,
  variant = 'num',
  tone = 'fg',
  style,
}: {
  children: string;
  /** True for a paper amount; false for live money or a total across both. */
  paper: boolean;
  variant?: TextVariant;
  tone?: TextTone;
  style?: StyleProp<TextStyle>;
}) {
  const { c } = useTheme();
  return (
    <Text
      variant={variant}
      tone={tone}
      style={[
        paper
          ? {
              textDecorationLine: 'underline',
              textDecorationStyle: 'dashed',
              textDecorationColor: c.fg3,
            }
          : null,
        style,
      ]}
    >
      {children}
    </Text>
  );
}
