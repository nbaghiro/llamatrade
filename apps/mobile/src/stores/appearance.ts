import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { secureStorage } from '../net/secure-storage';
import {
  DEFAULT_APPEARANCE,
  sanitizeAppearance,
  type AppearancePrefs,
  type DarkSurface,
  type LightSurface,
  type ModePreference,
  type ThemeMode,
} from '../theme/palette';

interface AppearanceState extends AppearancePrefs {
  setMode: (mode: ModePreference) => void;
  setDarkSurface: (surface: DarkSurface) => void;
  setLightSurface: (surface: LightSurface) => void;
  setAccent: (mode: ThemeMode, key: string) => void;
}

function prefsOf(state: AppearancePrefs): AppearancePrefs {
  return {
    mode: state.mode,
    darkSurface: state.darkSurface,
    lightSurface: state.lightSurface,
    darkAccent: state.darkAccent,
    lightAccent: state.lightAccent,
  };
}

/** Mode, surface and accent, matching the web AppearancePicker. */
export const useAppearanceStore = create<AppearanceState>()(
  persist<AppearanceState, [], [], AppearancePrefs>(
    (set, get) => {
      const update = (patch: Partial<AppearancePrefs>) =>
        set(sanitizeAppearance({ ...prefsOf(get()), ...patch }));
      return {
        ...DEFAULT_APPEARANCE,
        setMode: (mode) => update({ mode }),
        setDarkSurface: (darkSurface) => update({ darkSurface }),
        setLightSurface: (lightSurface) => update({ lightSurface }),
        setAccent: (mode, key) => update(mode === 'dark' ? { darkAccent: key } : { lightAccent: key }),
      };
    },
    {
      name: 'llamatrade-appearance',
      version: 1,
      storage: createJSONStorage(() => secureStorage),
      partialize: prefsOf,
      merge: (persisted, current) => ({ ...current, ...sanitizeAppearance(persisted) }),
    },
  ),
);
