import { useRef, type KeyboardEvent, type ReactNode } from 'react';

import { useResolvedTheme, useThemeStore, type ModePreference } from '../../store/theme';
import { accentsFor } from '../../theme/accents';
import { radioKeyTarget } from '../ui/radioKeys';
import { Segmented } from '../ui/Tabs';

const MODES: ReadonlyArray<{ key: ModePreference; label: string }> = [
  { key: 'system', label: 'System' },
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
];

/** Mode, surface and accent. Placed in Settings, Appearance. */
export function AppearancePicker() {
  const mode = useThemeStore((s) => s.mode);
  const darkSurface = useThemeStore((s) => s.darkSurface);
  const lightSurface = useThemeStore((s) => s.lightSurface);
  const setMode = useThemeStore((s) => s.setMode);
  const setDarkSurface = useThemeStore((s) => s.setDarkSurface);
  const setLightSurface = useThemeStore((s) => s.setLightSurface);
  const setAccent = useThemeStore((s) => s.setAccent);
  const resolved = useResolvedTheme();
  const shown = resolved.mode;
  const accents = accentsFor(shown);
  const swatches = useRef<Array<HTMLButtonElement | null>>([]);
  const checked = Math.max(
    0,
    accents.findIndex((a) => a.key === resolved.acc)
  );

  const onAccentKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = radioKeyTarget(e.key, index, accents.length);
    if (next === null) return;
    e.preventDefault();
    setAccent(shown, accents[next].key);
    swatches.current[next]?.focus();
  };

  return (
    <div className="grid gap-5">
      <Row
        title="Mode"
        help={mode === 'system' ? `Follows your device, which is ${shown} right now.` : undefined}
      >
        <Segmented label="Mode" options={MODES} value={mode} onChange={setMode} />
      </Row>

      <Row title={shown === 'dark' ? 'Dark surface' : 'Light surface'}>
        {shown === 'dark' ? (
          <Segmented
            label="Dark surface"
            options={[
              { key: 'black', label: 'Black' },
              { key: 'slate', label: 'Slate' },
            ]}
            value={darkSurface}
            onChange={setDarkSurface}
          />
        ) : (
          <Segmented
            label="Light surface"
            options={[
              { key: 'warm', label: 'Warm' },
              { key: 'white', label: 'White' },
            ]}
            value={lightSurface}
            onChange={setLightSurface}
          />
        )}
      </Row>

      <Row title="Accent" help={`Used for actions and selection in ${shown} mode.`}>
        <div role="radiogroup" aria-label="Accent" className="flex flex-wrap gap-2">
          {accents.map((a, i) => {
            const on = a.key === resolved.acc;
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
                onClick={() => setAccent(shown, a.key)}
                onKeyDown={(e) => onAccentKey(e, i)}
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
      </Row>
    </div>
  );
}

function Row({ title, help, children }: { title: string; help?: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)] sm:items-start">
      <div>
        <div className="text-[13px] font-medium text-fg">{title}</div>
        {help && <div className="mt-0.5 text-xs text-fg-3">{help}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}
