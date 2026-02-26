import { Moon, Sun } from 'lucide-react';

import { useThemeStore } from '../store/theme';

export function ThemeToggle() {
  const { theme, setTheme } = useThemeStore();

  // Determine if currently dark (either explicit dark or system preference)
  const isDark =
    theme === 'dark' ||
    (theme === 'system' && typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const toggleTheme = () => {
    // Simple toggle: if dark, switch to light; if light, switch to dark
    setTheme(isDark ? 'light' : 'dark');
  };

  return (
    <button
      onClick={toggleTheme}
      className="fixed bottom-4 right-4 z-50 p-3 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg hover:shadow-xl transition-all text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
}
