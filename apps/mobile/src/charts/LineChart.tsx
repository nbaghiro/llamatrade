import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Defs, G, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';

import { fonts, useTheme } from '../theme';
import { Text } from '../ui/Text';
import { areaPath, axisLabel, linePath, rangeOf, yFor } from './paths';

interface LineChartProps {
  values: readonly number[];
  /** Dashed comparison series drawn behind the main line on the same scale. */
  benchmark?: readonly number[];
  height?: number;
  /** Line colour; defaults to the accent. */
  color?: string;
  /** Soft gradient under the line. */
  fill?: boolean;
  /** Gridlines with value labels on the left. */
  axis?: boolean;
  /** Labels spaced evenly under the chart, e.g. first, middle and last date. */
  xLabels?: readonly string[];
  strokeWidth?: number;
}

const GRID_ROWS = 4;
const AXIS_W = 46;

/** Equity line in the accent with a soft fill; sizes itself to its container. */
export function LineChart({
  values,
  benchmark,
  height = 120,
  color,
  fill = true,
  axis = false,
  xLabels,
  strokeWidth = 1.75,
}: LineChartProps) {
  const { c, mode } = useTheme();
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(Math.round(e.nativeEvent.layout.width));

  const stroke = color ?? c.accent;
  const range = rangeOf(values, benchmark);
  const left = axis ? AXIS_W : 0;
  const plotW = Math.max(0, width - left);
  const pad = 4;
  const gridDash = mode === 'dark' ? '1 3' : undefined;
  const gradientId = `fill-${stroke.replace(/[^a-z0-9]/gi, '')}`;

  return (
    <View onLayout={onLayout}>
      {width > 0 && range ? (
        <Svg width={width} height={height}>
          <Defs>
            <LinearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={stroke} stopOpacity={mode === 'dark' ? 0.22 : 0.14} />
              <Stop offset="1" stopColor={stroke} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          {axis
            ? Array.from({ length: GRID_ROWS }, (_, i) => {
                const v = range.max - ((range.max - range.min) * i) / (GRID_ROWS - 1);
                const y = yFor(v, range, height, pad);
                return (
                  <SvgGridRow
                    key={i}
                    y={y}
                    x1={left}
                    x2={width}
                    label={axisLabel(v)}
                    lineColor={c.grid}
                    textColor={c.fg3}
                    dash={gridDash}
                  />
                );
              })
            : null}
          <G x={left}>
          {fill ? <Path d={areaPath(values, plotW, height, pad, range)} fill={`url(#${gradientId})`} /> : null}
          {benchmark && benchmark.length > 1 ? (
            <Path
              d={linePath(benchmark, plotW, height, pad, range)}
              fill="none"
              stroke={c.fg3}
              strokeWidth={1.25}
              strokeDasharray="3 3"
            />
          ) : null}
          <Path
            d={linePath(values, plotW, height, pad, range)}
            fill="none"
            stroke={stroke}
            strokeWidth={strokeWidth}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          </G>
        </Svg>
      ) : (
        <View style={{ height }} />
      )}
      {xLabels && xLabels.length ? (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, paddingLeft: left }}>
          {xLabels.map((l, i) => (
            <Text key={`${l}-${i}`} variant="numSmall" tone="fg3" style={{ fontSize: 10.5 }}>
              {l}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function SvgGridRow({
  y,
  x1,
  x2,
  label,
  lineColor,
  textColor,
  dash,
}: {
  y: number;
  x1: number;
  x2: number;
  label: string;
  lineColor: string;
  textColor: string;
  dash?: string;
}) {
  return (
    <>
      <Line x1={x1} y1={y} x2={x2} y2={y} stroke={lineColor} strokeWidth={1} strokeDasharray={dash} />
      <SvgText x={0} y={y + 3.5} fill={textColor} fontSize={10.5} fontFamily={fonts.mono}>
        {label}
      </SvgText>
    </>
  );
}
