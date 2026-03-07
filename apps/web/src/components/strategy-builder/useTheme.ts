import { useEffect, useState } from 'react';

import { getTheme, getCurrentThemeName, type ThemeName, type ThemeColors } from './block-theme';

/**
 * Hook that returns the current theme and re-renders when the theme changes.
 */
export function useBlockTheme(): ThemeColors {
  const [, setThemeName] = useState<ThemeName>(getCurrentThemeName());

  useEffect(() => {
    const handleThemeChange = (e: CustomEvent<ThemeName>) => {
      setThemeName(e.detail);
    };
    window.addEventListener('theme-change', handleThemeChange as EventListener);
    return () => window.removeEventListener('theme-change', handleThemeChange as EventListener);
  }, []);

  return getTheme();
}
