import { useResolvedTheme, useThemeStore } from '../../store/theme';
import type { ThemeMode } from '../../theme/accents';

const MODES: readonly { mode: ThemeMode; label: string }[] = [
  { mode: 'light', label: 'Light' },
  { mode: 'dark', label: 'Dark' },
];

/** Light or Dark, saved with the app's appearance setting. Follows the system until chosen. */
export function ThemeSwitch() {
  const { mode } = useResolvedTheme();
  const setMode = useThemeStore((s) => s.setMode);
  return (
    <div className="theme" role="group" aria-label="Appearance">
      {MODES.map((m) => (
        <button
          key={m.mode}
          type="button"
          aria-pressed={mode === m.mode}
          onClick={() => setMode(m.mode)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
