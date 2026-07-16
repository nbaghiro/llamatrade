import { View } from 'react-native';
import Svg, { Rect } from 'react-native-svg';

import { palette } from '../theme';
import { Display } from './index';

/**
 * Brand mark — ink box, orange frame, LT monogram.
 * Geometry mirrors packages/ui/src/components/Logo.tsx exactly (viewBox 0 0 120 120).
 */
export function Logo({ size = 32, showText = false }: { size?: number; showText?: boolean }) {
  const glyph = Math.round(size * 0.72);

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View
        style={{
          width: size,
          height: size,
          backgroundColor: palette.ink,
          borderWidth: 3,
          borderColor: palette.orange[500],
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Svg width={glyph} height={glyph} viewBox="0 0 120 120" fill="none">
          {/* L — bone */}
          <Rect x="30" y="26" width="17" height="52" fill="#f2efe6" />
          <Rect x="30" y="61" width="39" height="17" fill="#f2efe6" />
          {/* T — signal orange */}
          <Rect x="54" y="26" width="40" height="17" fill="#ff4d1c" />
          <Rect x="68" y="26" width="17" height="52" fill="#ff4d1c" />
        </Svg>
      </View>

      {showText ? <Display size={Math.round(size * 0.62)}>LlamaTrade</Display> : null}
    </View>
  );
}
