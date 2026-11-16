import { useSyncExternalStore } from 'react';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useShallow } from 'zustand/react/shallow';

import { DEFAULT_ACCENT, isAccentFor, type ThemeMode } from '../theme/accents';

export type ModePreference = 'system' | ThemeMode;
export type DarkSurface = 'slate' | 'black';
export type LightSurface = 'warm' | 'white';

export interface ThemePrefs {
  mode: ModePreference;
  darkSurface: DarkSurface;
  lightSurface: LightSurface;
  darkAccent: string;
  lightAccent: string;
}

/** The attributes written to <html>: data-mode, data-theme, data-light and data-acc. */
export interface ResolvedTheme {
  mode: ThemeMode;
  theme: DarkSurface;
  light: LightSurface;
  acc: string;
}

export interface ThemeRoot {
  dataset: Record<string, string | undefined>;
}

export interface SchemeQuery {
  matches: boolean;
  addEventListener: (type: 'change', listener: () => void) => void;
  removeEventListener: (type: 'change', listener: () => void) => void;
}

export const THEME_STORAGE_KEY = 'llamatrade-theme';
export const LIGHT_SCHEME_QUERY = '(prefers-color-scheme: light)';

export const DEFAULT_THEME: ThemePrefs = {
  mode: 'system',
  darkSurface: 'slate',
  lightSurface: 'white',
  darkAccent: DEFAULT_ACCENT.dark,
  lightAccent: DEFAULT_ACCENT.light,
};

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.find((a) => a === value) ?? fallback;
}

/** Coerces anything read from storage into valid preferences, field by field. */
export function sanitizeTheme(raw: unknown): ThemePrefs {
  const r = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
  return {
    mode: pick(r.mode, ['system', 'light', 'dark'] as const, DEFAULT_THEME.mode),
    darkSurface: pick(r.darkSurface, ['slate', 'black'] as const, DEFAULT_THEME.darkSurface),
    lightSurface: pick(r.lightSurface, ['warm', 'white'] as const, DEFAULT_THEME.lightSurface),
    darkAccent: isAccentFor('dark', r.darkAccent) ? r.darkAccent : DEFAULT_THEME.darkAccent,
    lightAccent: isAccentFor('light', r.lightAccent) ? r.lightAccent : DEFAULT_THEME.lightAccent,
  };
}

export function resolveTheme(prefs: ThemePrefs, systemPrefersLight: boolean): ResolvedTheme {
  const mode: ThemeMode =
    prefs.mode === 'system' ? (systemPrefersLight ? 'light' : 'dark') : prefs.mode;
  return {
    mode,
    theme: prefs.darkSurface,
    light: prefs.lightSurface,
    acc: mode === 'dark' ? prefs.darkAccent : prefs.lightAccent,
  };
}

export function applyTheme(resolved: ResolvedTheme, root: ThemeRoot): void {
  root.dataset.mode = resolved.mode;
  root.dataset.theme = resolved.theme;
  root.dataset.light = resolved.light;
  root.dataset.acc = resolved.acc;
}

/** Calls `onChange` whenever the OS scheme flips; returns the unsubscribe. */
export function watchScheme(query: SchemeQuery, onChange: (prefersLight: boolean) => void) {
  const listener = () => onChange(query.matches);
  query.addEventListener('change', listener);
  return () => query.removeEventListener('change', listener);
}

function schemeQuery(): SchemeQuery | null {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(LIGHT_SCHEME_QUERY)
    : null;
}

function applyToDocument(prefs: ThemePrefs): void {
  if (typeof document === 'undefined') return;
  applyTheme(resolveTheme(prefs, schemeQuery()?.matches ?? false), document.documentElement);
}

interface ThemeState extends ThemePrefs {
  resolved: () => ResolvedTheme;
  setMode: (mode: ModePreference) => void;
  setDarkSurface: (surface: DarkSurface) => void;
  setLightSurface: (surface: LightSurface) => void;
  setAccent: (mode: ThemeMode, key: string) => void;
}

function prefsOf(state: ThemePrefs): ThemePrefs {
  return {
    mode: state.mode,
    darkSurface: state.darkSurface,
    lightSurface: state.lightSurface,
    darkAccent: state.darkAccent,
    lightAccent: state.lightAccent,
  };
}

export const useThemeStore = create<ThemeState>()(
  persist<ThemeState, [], [], ThemePrefs>(
    (set, get) => {
      const update = (patch: Partial<ThemePrefs>) => {
        const next = sanitizeTheme({ ...prefsOf(get()), ...patch });
        set(next);
        applyToDocument(next);
      };
      return {
        ...DEFAULT_THEME,
        resolved: () => resolveTheme(prefsOf(get()), schemeQuery()?.matches ?? false),
        setMode: (mode) => update({ mode }),
        setDarkSurface: (darkSurface) => update({ darkSurface }),
        setLightSurface: (lightSurface) => update({ lightSurface }),
        setAccent: (mode, key) =>
          update(mode === 'dark' ? { darkAccent: key } : { lightAccent: key }),
      };
    },
    {
      name: THEME_STORAGE_KEY,
      version: 1,
      partialize: prefsOf,
      migrate: (persisted) => sanitizeTheme(persisted),
      merge: (persisted, current) => ({ ...current, ...sanitizeTheme(persisted) }),
      onRehydrateStorage: () => (state) => {
        if (state) applyToDocument(prefsOf(state));
      },
    }
  )
);

function subscribeScheme(onChange: () => void) {
  const q = schemeQuery();
  return q ? watchScheme(q, onChange) : () => undefined;
}

/** The theme as it renders right now, following OS scheme changes in system mode. */
export function useResolvedTheme(): ResolvedTheme {
  const prefersLight = useSyncExternalStore(
    subscribeScheme,
    () => schemeQuery()?.matches ?? false,
    () => false
  );
  const prefs = useThemeStore(useShallow(prefsOf));
  return resolveTheme(prefs, prefersLight);
}

const query = schemeQuery();
if (query) {
  watchScheme(query, () => {
    const state = useThemeStore.getState();
    if (state.mode === 'system') applyToDocument(prefsOf(state));
  });
}
