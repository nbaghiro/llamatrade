import { Moon, Monitor, Sun } from 'lucide-react';

import {
  useResolvedTheme,
  useThemeStore,
  type DarkSurface,
  type LightSurface,
  type ModePreference,
} from '../../store/theme';
import type { ThemeMode } from '../../theme/accents';
import { LogoMark } from '../common/Logo';
import { Segmented } from '../ui/Tabs';

import { AccentDots } from './AppearancePicker';
import { accentLabel, previewVars } from './previewTheme';

const MODE_ICON = { light: Sun, dark: Moon, system: Monitor } as const;
const MODE_LABEL: Record<ModePreference, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
};

/** Light, Dark or System, with icons, for the Appearance header. */
export function ModeSegment() {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  return (
    <Segmented
      label="Mode"
      value={mode}
      onChange={setMode}
      options={(['light', 'dark', 'system'] as const).map((key) => {
        const Icon = MODE_ICON[key];
        return {
          key,
          label: (
            <span className="inline-flex items-center gap-1.5">
              <Icon aria-hidden="true" className="h-3.5 w-3.5" />
              {MODE_LABEL[key]}
            </span>
          ),
        };
      })}
    />
  );
}

const CURVE = 'M0 60 L40 52 L80 56 L120 40 L160 44 L200 26 L240 30 L300 10';

/** One small app window drawn in a surface and accent; it shows shapes, never figures. */
function SurfaceWindow({
  mode,
  surface,
  name,
  accent,
  selected,
  inUse,
  onSelect,
}: {
  mode: ThemeMode;
  surface: DarkSurface | LightSurface;
  name: string;
  accent: string;
  selected: boolean;
  inUse: boolean;
  onSelect: () => void;
}) {
  const ring = !selected
    ? 'border-line hover:border-line-strong'
    : inUse
      ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]'
      : 'border-line-strong shadow-[0_0_0_3px_rgb(var(--sunk))]';
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-label={`${name}, ${mode}`}
      onClick={onSelect}
      className={`min-w-0 overflow-hidden rounded-panel border bg-panel text-left transition-shadow ${ring}`}
    >
      <div className="relative h-[132px] overflow-hidden bg-sunk">
        <div
          aria-hidden="true"
          style={previewVars(mode, surface, accent)}
          className="absolute bottom-[-12px] left-3.5 right-0 top-3.5 overflow-hidden rounded-tl-[8px] border border-line bg-canvas text-fg"
        >
          <div className="flex h-7 items-center gap-2 border-b border-line bg-panel px-2.5">
            <LogoMark size={14} />
            <i className="ml-1.5 h-1.5 w-7 rounded-full bg-accent" />
            <i className="h-1.5 w-7 rounded-full bg-line-strong" />
          </div>
          <div className="grid gap-1.5 px-3 pt-2.5">
            <span className="text-[8.5px] font-medium uppercase tracking-[0.08em] text-fg-3">
              Total equity
            </span>
            <i className="block h-2.5 w-24 rounded-[3px] bg-fg/80" />
            <svg viewBox="0 0 300 70" preserveAspectRatio="none" className="h-[52px] w-full">
              <path d={CURVE} fill="none" stroke="rgb(var(--accent))" strokeWidth="2" />
            </svg>
          </div>
        </div>
      </div>
      <span className="flex items-center gap-2 border-t border-line px-3 py-2 text-[12.5px]">
        <b className="font-semibold text-fg">{name}</b>
        <span className="ml-auto truncate text-[11.5px] text-fg-3">
          {accentLabel(mode, accent)}
        </span>
      </span>
    </button>
  );
}

const DARK: ReadonlyArray<{ key: DarkSurface; name: string }> = [
  { key: 'slate', name: 'Graphite' },
  { key: 'black', name: 'Black' },
];
const LIGHT: ReadonlyArray<{ key: LightSurface; name: string }> = [
  { key: 'white', name: 'White' },
  { key: 'warm', name: 'Warm' },
];

function ModeColumn({ mode }: { mode: ThemeMode }) {
  const resolved = useResolvedTheme();
  const darkSurface = useThemeStore((s) => s.darkSurface);
  const lightSurface = useThemeStore((s) => s.lightSurface);
  const darkAccent = useThemeStore((s) => s.darkAccent);
  const lightAccent = useThemeStore((s) => s.lightAccent);
  const setDarkSurface = useThemeStore((s) => s.setDarkSurface);
  const setLightSurface = useThemeStore((s) => s.setLightSurface);
  const inUse = resolved.mode === mode;
  const accent = mode === 'dark' ? darkAccent : lightAccent;
  const label = mode === 'dark' ? 'Dark' : 'Light';

  return (
    <div className="grid content-start gap-2.5">
      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-fg-3">
        {label}
        {inUse ? ' · in use now' : ''}
      </div>
      <div role="radiogroup" aria-label={`${label} surface`} className="grid grid-cols-2 gap-3">
        {mode === 'dark'
          ? DARK.map((s) => (
              <SurfaceWindow
                key={s.key}
                mode="dark"
                surface={s.key}
                name={s.name}
                accent={accent}
                selected={darkSurface === s.key}
                inUse={inUse}
                onSelect={() => setDarkSurface(s.key)}
              />
            ))
          : LIGHT.map((s) => (
              <SurfaceWindow
                key={s.key}
                mode="light"
                surface={s.key}
                name={s.name}
                accent={accent}
                selected={lightSurface === s.key}
                inUse={inUse}
                onSelect={() => setLightSurface(s.key)}
              />
            ))}
      </div>
      <div className="px-0.5 py-1">
        <AccentDots mode={mode} />
      </div>
    </div>
  );
}

/** All four surfaces as small app windows, dark beside light, each in its mode's accent (appearance2 B). */
export function AppearanceGrid() {
  return (
    <div className="grid gap-4">
      <div className="grid gap-6 md:grid-cols-2">
        <ModeColumn mode="dark" />
        <ModeColumn mode="light" />
      </div>
      <p className="m-0 text-[12px] text-fg-3">
        The outlined window in each mode is the one you&apos;ll see. Gains, losses and warnings keep
        their colours in every combination.
      </p>
    </div>
  );
}
