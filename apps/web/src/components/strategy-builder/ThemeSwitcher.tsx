import { Palette } from 'lucide-react';
import { useEffect, useState } from 'react';

import {
  themes,
  setTheme,
  getCurrentThemeName,
  type ThemeName,
} from './block-theme';

export function ThemeSwitcher() {
  const [currentTheme, setCurrentTheme] = useState<ThemeName>(getCurrentThemeName());
  const [isOpen, setIsOpen] = useState(false);

  // Force re-render when theme changes
  useEffect(() => {
    const handleThemeChange = (e: CustomEvent<ThemeName>) => {
      setCurrentTheme(e.detail);
    };
    window.addEventListener('theme-change', handleThemeChange as EventListener);
    return () => window.removeEventListener('theme-change', handleThemeChange as EventListener);
  }, []);

  const handleThemeSelect = (name: ThemeName) => {
    setTheme(name);
    setIsOpen(false);
  };

  const themeEntries = Object.entries(themes) as [ThemeName, typeof themes[ThemeName]][];

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
      >
        <Palette className="w-4 h-4" />
        <span>Theme: {themes[currentTheme].name}</span>
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown - opens upward */}
          <div className="absolute left-0 bottom-full mb-1 z-50 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg overflow-hidden">
            <div className="p-2 border-b border-gray-100 dark:border-gray-700">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Block Color Themes
              </span>
            </div>
            <div className="p-1 max-h-80 overflow-y-auto">
              {themeEntries.map(([name, theme]) => (
                <button
                  key={name}
                  onClick={() => handleThemeSelect(name)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-left transition-colors
                    ${currentTheme === name
                      ? 'bg-gray-100 dark:bg-gray-700'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }
                  `}
                >
                  {/* Color preview dots */}
                  <div className="flex gap-1">
                    <div className={`w-3 h-3 rounded-full ${theme.weight.bg.split(' ')[0]}`} />
                    <div className={`w-3 h-3 rounded-full ${theme.ifBlock.bg.split(' ')[0]}`} />
                    <div className={`w-3 h-3 rounded-full ${theme.elseBlock.bg.split(' ')[0]}`} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className={`text-sm font-medium ${currentTheme === name ? 'text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>
                      {theme.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {theme.description}
                    </div>
                  </div>

                  {currentTheme === name && (
                    <div className="w-2 h-2 rounded-full bg-blue-500" />
                  )}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
