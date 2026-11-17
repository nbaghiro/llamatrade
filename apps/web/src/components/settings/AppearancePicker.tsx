import { useRef, type KeyboardEvent, type ReactNode } from 'react';

import {
  useResolvedTheme,
  useThemeStore,
  type DarkSurface,
  type LightSurface,
  type ModePreference,
} from '../../store/theme';
import { accentsFor, type ThemeMode } from '../../theme/accents';
import { radioKeyTarget } from '../ui/radioKeys';
import { Segmented } from '../ui/Tabs';

import { SURFACES, accentLabel } from './previewTheme';

const MODES: ReadonlyArray<{ key: ModePreference; label: string }> = [
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
  { key: 'system', label: 'System' },
];

const DARK_SURFACES: ReadonlyArray<{ key: DarkSurface; label: string }> = [
  { key: 'slate', label: 'Slate' },
  { key: 'black', label: 'Black' },
];
const LIGHT_SURFACES: ReadonlyArray<{ key: LightSurface; label: string }> = [
  { key: 'white', label: 'White' },
  { key: 'warm', label: 'Warm' },
];

function SurfaceChips<K extends DarkSurface | LightSurface>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: ReadonlyArray<{ key: K; label: string }>;
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.key)}
            className={`inline-flex h-8 items-center gap-2 rounded-full border px-3 text-[12.5px] transition-colors ${
              on ? 'border-fg text-fg' : 'border-line-strong text-fg-2 hover:text-fg'
            }`}
          >
            <i
              aria-hidden="true"
              className="h-3.5 w-3.5 rounded-full border border-line-strong"
              style={{ background: `rgb(${SURFACES[o.key].canvas})` }}
            />
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function AccentDots({ mode }: { mode: ThemeMode }) {
  const darkAccent = useThemeStore((s) => s.darkAccent);
  const lightAccent = useThemeStore((s) => s.lightAccent);
  const setAccent = useThemeStore((s) => s.setAccent);
  const current = mode === 'dark' ? darkAccent : lightAccent;
  const accents = accentsFor(mode);
  const swatches = useRef<Array<HTMLButtonElement | null>>([]);
  const checked = Math.max(
    0,
    accents.findIndex((a) => a.key === current)
  );

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = radioKeyTarget(e.key, index, accents.length);
    if (next === null) return;
    e.preventDefault();
    setAccent(mode, accents[next].key);
    swatches.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={`Accent in ${mode}`} className="flex flex-wrap gap-2">
      {accents.map((a, i) => {
        const on = a.key === current;
        return (
          <button
            key={a.key}
            ref={(el) => {
              swatches.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            aria-label={a.label}
            title={a.label}
            tabIndex={i === checked ? 0 : -1}
            onClick={() => setAccent(mode, a.key)}
            onKeyDown={(e) => onKey(e, i)}
            className="h-6 w-6 rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[5px] focus-visible:outline-accent"
            style={{
              background: a.swatch,
              boxShadow: on
                ? '0 0 0 2px rgb(var(--panel)), 0 0 0 3.5px rgb(var(--fg-2))'
                : 'inset 0 0 0 1px rgb(127 127 127 / 0.35)',
            }}
          />
        );
      })}
    </div>
  );
}

/**
 * Mode, then a surface and an accent. With `both`, the controls for dark and light sit together
 * (appearance2 A); otherwise only the mode now showing.
 */
export function AppearancePicker({ both = false }: { both?: boolean }) {
  const mode = useThemeStore((s) => s.mode);
  const darkSurface = useThemeStore((s) => s.darkSurface);
  const lightSurface = useThemeStore((s) => s.lightSurface);
  const darkAccent = useThemeStore((s) => s.darkAccent);
  const lightAccent = useThemeStore((s) => s.lightAccent);
  const setMode = useThemeStore((s) => s.setMode);
  const setDarkSurface = useThemeStore((s) => s.setDarkSurface);
  const setLightSurface = useThemeStore((s) => s.setLightSurface);
  const resolved = useResolvedTheme();
  const showDark = both || resolved.mode === 'dark';
  const showLight = both || resolved.mode === 'light';

  return (
    <div className="grid content-start gap-5">
      <Row
        title="Mode"
        help={
          mode === 'system'
            ? `Follows your device, which is ${resolved.mode} right now.`
            : undefined
        }
      >
        <Segmented label="Mode" options={MODES} value={mode} onChange={setMode} />
      </Row>
      {showDark && (
        <>
          <Row title="Dark surface">
            <SurfaceChips
              label="Dark surface"
              options={DARK_SURFACES}
              value={darkSurface}
              onChange={setDarkSurface}
            />
          </Row>
          <Row title="Accent in dark" help={accentLabel('dark', darkAccent)}>
            <AccentDots mode="dark" />
          </Row>
        </>
      )}
      {showLight && (
        <>
          <Row title="Light surface">
            <SurfaceChips
              label="Light surface"
              options={LIGHT_SURFACES}
              value={lightSurface}
              onChange={setLightSurface}
            />
          </Row>
          <Row title="Accent in light" help={accentLabel('light', lightAccent)}>
            <AccentDots mode="light" />
          </Row>
        </>
      )}
    </div>
  );
}

function Row({ title, help, children }: { title: string; help?: string; children: ReactNode }) {
  return (
    <div className="grid gap-2">
      <div className="text-[12px] font-medium text-fg-2">{title}</div>
      {children}
      {help && <div className="text-xs text-fg-3">{help}</div>}
    </div>
  );
}
