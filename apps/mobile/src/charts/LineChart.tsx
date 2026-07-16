import Svg, { Path } from 'react-native-svg';

import { palette } from '../theme';
import { areaPath, linePath } from './paths';

interface LineChartProps {
  values: number[];
  /** Optional dashed benchmark overlay drawn behind the main line. */
  benchmark?: number[];
  width?: number;
  height?: number;
  color?: string;
  /** rgba fill under the line; omit for a bare line (sparkline). */
  fill?: string;
  strokeWidth?: number;
}

/** Responsive equity / sparkline chart — react-native-svg port of the web SVG. */
export function LineChart({
  values,
  benchmark,
  width = 300,
  height = 84,
  color = palette.orange[500],
  fill,
  strokeWidth = 2.5,
}: LineChartProps) {
  return (
    <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {fill ? <Path d={areaPath(values, width, height)} fill={fill} /> : null}
      {benchmark ? (
        <Path
          d={linePath(benchmark, width, height)}
          fill="none"
          stroke={palette.gray[400]}
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
      ) : null}
      <Path d={linePath(values, width, height)} fill="none" stroke={color} strokeWidth={strokeWidth} />
    </Svg>
  );
}
