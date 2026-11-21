/**
 * Sparkline props:
 *   values: readonly number[]   the series, oldest first; fewer than two finite values draws nothing
 *   width?: number              default 64
 *   height?: number             default 22
 *   color?: string              default the accent
 *   muted?: boolean             draws in fg3, for stopped or paused records
 *   strokeWidth?: number        default 1.4
 */
import { View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { useTheme } from '../theme';
import { linePath } from './paths';

export interface SparklineProps {
  values: readonly number[];
  width?: number;
  height?: number;
  color?: string;
  muted?: boolean;
  strokeWidth?: number;
}

/** A small line without axes, for a row's shape at a glance. */
export function Sparkline({ values, width = 64, height = 22, color, muted = false, strokeWidth = 1.4 }: SparklineProps) {
  const { c } = useTheme();
  const d = linePath(values, width, height, 2);
  return (
    <View style={{ width, height }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {d ? (
        <Svg width={width} height={height}>
          <Path
            d={d}
            fill="none"
            stroke={muted ? c.fg3 : (color ?? c.accent)}
            strokeWidth={strokeWidth}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </Svg>
      ) : null}
    </View>
  );
}
