import { useColorScheme, StyleSheet, type ViewStyle } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { useAppearanceStore } from '../stores/appearance';
import {
  colorsFor,
  resolveMode,
  type AppearancePrefs,
  type Colors,
  type ThemeMode,
} from './palette';

export * from './palette';

/** Family names registered with expo-font in app/_layout.tsx; one family per static weight. */
export const fonts = {
  sans: 'Geist-Regular',
  medium: 'Geist-Medium',
  semibold: 'Geist-SemiBold',
  bold: 'Geist-Bold',
  mono: 'GeistMono-Regular',
  monoMedium: 'GeistMono-Medium',
  monoSemibold: 'GeistMono-SemiBold',
} as const;

export const radius = {
  xs: 4,
  sm: 6,
  md: 8,
  lg: 12,
  sheet: 18,
  pill: 999,
} as const;

/** Horizontal page gutter and the gap between stacked blocks. */
export const space = { gutter: 20, gap: 14 } as const;

export interface Theme {
  mode: ThemeMode;
  c: Colors;
  shadow: { sm: ViewStyle; md: ViewStyle; lg: ViewStyle };
}

function shadows(mode: ThemeMode): Theme['shadow'] {
  const dark = mode === 'dark';
  const color = dark ? '#000000' : '#111418';
  return {
    sm: {
      shadowColor: color,
      shadowOffset: { width: 0, height: 1 },
      shadowOpacity: dark ? 0.35 : 0.06,
      shadowRadius: 2,
    },
    md: {
      shadowColor: color,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: dark ? 0.4 : 0.1,
      shadowRadius: 10,
    },
    lg: {
      shadowColor: color,
      shadowOffset: { width: 0, height: -8 },
      shadowOpacity: dark ? 0.55 : 0.16,
      shadowRadius: 24,
    },
  };
}

const themeCache = new Map<string, Theme>();

/** One stable object per resolved appearance, so memoised styles can key on identity. */
export function themeFor(prefs: AppearancePrefs, mode: ThemeMode): Theme {
  const key = `${mode}:${prefs.darkSurface}:${prefs.lightSurface}:${prefs.darkAccent}:${prefs.lightAccent}`;
  let theme = themeCache.get(key);
  if (!theme) {
    theme = { mode, c: colorsFor(prefs, mode), shadow: shadows(mode) };
    themeCache.set(key, theme);
  }
  return theme;
}

const selectPrefs = (s: AppearancePrefs): AppearancePrefs => ({
  mode: s.mode,
  darkSurface: s.darkSurface,
  lightSurface: s.lightSurface,
  darkAccent: s.darkAccent,
  lightAccent: s.lightAccent,
});

/** The theme as it renders now: the saved appearance, following the device in System mode. */
export function useTheme(): Theme {
  const scheme = useColorScheme();
  const prefs = useAppearanceStore(useShallow(selectPrefs));
  return themeFor(prefs, resolveMode(prefs.mode, scheme));
}

/** Builds a themed StyleSheet hook; each theme's sheet is created once. */
export function makeStyles<T extends StyleSheet.NamedStyles<T>>(factory: (t: Theme) => T): () => T {
  const cache = new WeakMap<Theme, T>();
  return function useStyles(): T {
    const t = useTheme();
    let sheet = cache.get(t);
    if (!sheet) {
      sheet = StyleSheet.create(factory(t));
      cache.set(t, sheet);
    }
    return sheet;
  };
}
