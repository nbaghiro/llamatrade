import { StyleSheet, View } from 'react-native';

import { semantic } from '../theme';

/**
 * GridBackground — the Monolith "exposed grid" scaffold ported from web
 * (.bg-grid / marketing .grid-overlay): faint ink hairlines splitting the
 * surface into equal columns, pinned behind content and non-interactive, so it
 * shows through the bone gaps between cards. Six columns matches the ≤720px
 * marketing/web breakpoint.
 */
export function GridBackground({
  columns = 6,
  color = semantic.line,
}: {
  columns?: number;
  color?: string;
}) {
  return (
    <View style={[StyleSheet.absoluteFill, { flexDirection: 'row' }]} pointerEvents="none">
      {Array.from({ length: columns }, (_, i) => (
        <View key={i} style={{ flex: 1, borderLeftWidth: StyleSheet.hairlineWidth, borderColor: color }} />
      ))}
    </View>
  );
}
