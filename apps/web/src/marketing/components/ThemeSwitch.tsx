import { Moon, Sun } from 'lucide-react';

import { useResolvedTheme, useThemeStore } from '../../store/theme';

/** One icon button that flips light and dark, saved with the app's appearance setting. */
export function ThemeSwitch() {
  const { mode } = useResolvedTheme();
  const setMode = useThemeStore((s) => s.setMode);
  const next = mode === 'dark' ? 'light' : 'dark';
  const Icon = mode === 'dark' ? Moon : Sun;
  return (
    <button
      type="button"
      className="theme"
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      onClick={() => setMode(next)}
    >
      <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}
