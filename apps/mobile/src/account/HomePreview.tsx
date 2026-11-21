import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { useShallow } from 'zustand/react/shallow';

import { exampleBacktest } from '../auth/example';
import { linePath } from '../charts/paths';
import { useAppearanceStore } from '../stores/appearance';
import { fonts, themeFor, type AppearancePrefs, type ThemeMode } from '../theme';
import { LogoMark, Text } from '../ui';

const selectPrefs = (s: AppearancePrefs): AppearancePrefs => ({
  mode: s.mode,
  darkSurface: s.darkSurface,
  lightSurface: s.lightSurface,
  darkAccent: s.darkAccent,
  lightAccent: s.lightAccent,
});

const money = (v: number) => `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const LANE_SPANS = [
  { left: 0, right: 0.3 },
  { left: 0.38, right: 0 },
] as const;

/** A small Home in the chosen surface and accent for `mode`: your total, curve and session lanes. */
export function HomePreview({ mode }: { mode: ThemeMode }) {
  const prefs = useAppearanceStore(useShallow(selectPrefs));
  const { c } = themeFor(prefs, mode);
  const totalEquity = useDashboardStore((s) => s.totalEquity);
  const curve = useDashboardStore((s) => s.portfolioCurve);
  const strategies = useDashboardStore((s) => s.strategies);
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));

  const real = curve.length >= 2;
  const values = real ? curve.map((p) => p.value) : exampleBacktest().strategy.filter((_, i) => i % 6 === 0);
  const H = 86;
  const line = w > 0 ? linePath(values, w, H, 4) : '';
  const names = strategies.length ? strategies.slice(0, 2).map((st) => st.name) : ['Session one', 'Session two'];
  const gradient = `pv-${mode}`;

  return (
    <View style={{ borderRadius: 14, borderWidth: 1, borderColor: c.lineStrong, backgroundColor: c.canvas, overflow: 'hidden' }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingTop: 12 }}>
        <LogoMark size={16} bold color={c.fg} />
        <View style={{ flex: 1 }} />
        <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: c.accentSoft }} />
      </View>
      <View style={{ paddingHorizontal: 14, paddingTop: 10, gap: 2 }}>
        <Text variant="caption" color={c.fg3}>Total equity</Text>
        <Text variant="numLarge" color={c.fg} style={{ fontFamily: fonts.monoSemibold }}>
          {real && totalEquity > 0 ? money(totalEquity) : 'Preview'}
        </Text>
      </View>
      <View onLayout={onLayout} style={{ marginTop: 6 }}>
        {line ? (
          <Svg width={w} height={H}>
            <Defs>
              <LinearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0" stopColor={c.accent} stopOpacity={mode === 'dark' ? 0.25 : 0.16} />
                <Stop offset="1" stopColor={c.accent} stopOpacity={0} />
              </LinearGradient>
            </Defs>
            <Path d={`${line} L${w},${H} L0,${H} Z`} fill={`url(#${gradient})`} />
            <Path d={line} stroke={c.accent} strokeWidth={2} fill="none" />
          </Svg>
        ) : null}
      </View>
      <View style={{ paddingHorizontal: 14, paddingVertical: 10, gap: 8, backgroundColor: c.panel, borderTopWidth: 1, borderColor: c.line }}>
        {names.map((name, i) => {
          const span = LANE_SPANS[i % LANE_SPANS.length];
          return (
            <View key={name} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Text variant="caption" color={c.fg2} numberOfLines={1} style={{ width: 120 }}>
                {name}
              </Text>
              <View style={{ flex: 1, height: 2, backgroundColor: c.line }}>
                <View
                  style={{
                    position: 'absolute',
                    left: `${span.left * 100}%`,
                    right: `${span.right * 100}%`,
                    height: 2,
                    backgroundColor: i === 0 ? c.accent : c.fg3,
                  }}
                />
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}
