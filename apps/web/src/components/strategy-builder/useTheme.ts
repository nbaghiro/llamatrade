import { getTheme, type ThemeColors } from './block-theme';

/**
 * Hook that returns the current theme.
 */
export function useBlockTheme(): ThemeColors {
  return getTheme();
}
