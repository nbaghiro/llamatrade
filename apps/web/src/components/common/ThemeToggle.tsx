import { Moon, Sun } from 'lucide-react';

import { useThemeStore } from '../../store/theme';

interface ThemeToggleProps {
  /** Render inline (for header) vs floating (fixed position) */
  variant?: 'inline' | 'floating';
  /** Position for floating variant */
  position?: 'bottom-left' | 'bottom-right';
}

export function ThemeToggle({ variant = 'floating', position = 'bottom-right' }: ThemeToggleProps) {
  const { theme, setTheme } = useThemeStore();

  // Determine if currently dark (either explicit dark or system preference)
  const isDark =
    theme === 'dark' ||
    (theme === 'system' && typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const toggleTheme = () => {
    // Simple toggle: if dark, switch to light; if light, switch to dark
    setTheme(isDark ? 'light' : 'dark');
  };

  const baseClasses = 'transition-all text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100';

  if (variant === 'inline') {
    return (
      <button
        onClick={toggleTheme}
        className={`p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 ${baseClasses}`}
        title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>
    );
  }

  const positionClasses = position === 'bottom-left' ? 'bottom-6 left-6' : 'bottom-6 right-6';

  return (
    <button
      onClick={toggleTheme}
      className={`fixed ${positionClasses} z-50 p-3 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg hover:shadow-xl ${baseClasses}`}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
}
