import { memo, useMemo } from 'react';
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import Svg, { Defs, Line, LinearGradient, Path, RadialGradient, Rect, Stop } from 'react-native-svg';

import { useTheme } from '../theme';
import { candleArt, hashSeed } from './candleArt';

/** How strongly a screen shows its art: off, soft behind dense pages, full, or bold (taller and stronger). */
export type ArtIntensity = 'off' | 'soft' | 'full' | 'bold';

const STRENGTH: Record<ArtIntensity, number> = { off: 0, soft: 0.6, full: 1, bold: 1.45 };

/** Art height for a window: the top half of the screen, at most 460pt. */
export function artHeight(windowHeight: number): number {
  return Math.round(Math.min(460, Math.max(240, windowHeight * 0.52)));
}

/** Art height for `bold`: most of the screen, so the candles run on behind the first cards. */
export function boldArtHeight(windowHeight: number): number {
  return Math.round(Math.min(720, Math.max(320, windowHeight * 0.8)));
}

interface Props {
  /** A screen's name or number; the same seed always draws the same chart. */
  seed: string | number;
  intensity?: ArtIntensity;
  /** Defaults to the window width. */
  width?: number;
  /** Defaults to `artHeight` of the window. */
  height?: number;
}

/**
 * Faint candlesticks in the accent behind a screen's top, fading into the canvas, with a soft
 * glow from one side and the area behind the title kept clear. Three paths, drawn once.
 */
export const CandleBackdrop = memo(function CandleBackdrop({ seed, intensity = 'full', width, height }: Props) {
  const { c, art } = useTheme();
  const win = useWindowDimensions();
  const W = Math.round(width ?? win.width);
  const H = Math.round(height ?? artHeight(win.height));
  const n = hashSeed(seed);
  const shape = useMemo(() => candleArt(n, W, H), [n, W, H]);
  const k = STRENGTH[intensity];
  if (k === 0 || W === 0 || H === 0) return null;

  const glowX = shape.glowSide === 'left' ? 0 : W;
  return (
    <View pointerEvents="none" style={[styles.box, { height: H }]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Svg width={W} height={H}>
        <Defs>
          <RadialGradient id="glow" cx={glowX} cy={H * 0.28} rx={W * 0.85} ry={H * 0.7} fx={glowX} fy={H * 0.28} gradientUnits="userSpaceOnUse">
            <Stop offset="0" stopColor={art.glow} stopOpacity={art.glowOpacity * k} />
            <Stop offset="1" stopColor={art.glow} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id="clear" cx={W * 0.28} cy={H * 0.3} rx={W * 0.52} ry={H * 0.24} fx={W * 0.28} fy={H * 0.3} gradientUnits="userSpaceOnUse">
            <Stop offset="0" stopColor={c.canvas} stopOpacity={0.75} />
            <Stop offset="0.55" stopColor={c.canvas} stopOpacity={0.35} />
            <Stop offset="1" stopColor={c.canvas} stopOpacity={0} />
          </RadialGradient>
          <LinearGradient id="fade" x1="0" y1="0" x2="0" y2={H} gradientUnits="userSpaceOnUse">
            <Stop offset={intensity === 'bold' ? 0.55 : 0.3} stopColor={c.canvas} stopOpacity={0} />
            <Stop offset="0.96" stopColor={c.canvas} stopOpacity={1} />
          </LinearGradient>
        </Defs>
        <Rect x={0} y={0} width={W} height={H} fill="url(#glow)" />
        {shape.levels.map((y) => (
          <Line key={y} x1={0} x2={W} y1={y} y2={y} stroke={art.color} strokeOpacity={art.opacity * 0.7 * k} strokeWidth={1} strokeDasharray="1 4" />
        ))}
        <Path d={shape.wicks} stroke={art.color} strokeOpacity={art.opacity * k} strokeWidth={1} />
        <Path d={shape.up} stroke={art.color} strokeOpacity={art.opacity * k} strokeWidth={1} fill="none" />
        <Path d={shape.down} fill={art.color} fillOpacity={art.opacity * k} />
        <Rect x={0} y={0} width={W} height={H} fill="url(#clear)" />
        <Rect x={0} y={0} width={W} height={H} fill="url(#fade)" />
      </Svg>
    </View>
  );
});

const styles = StyleSheet.create({
  box: { position: 'absolute', top: 0, left: 0, right: 0 },
});
