import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// Monolith is light-only (dark mode retired); the store keeps its original API but always forces light.
type Theme = 'light';

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

function applyLight() {
  document.documentElement.classList.remove('dark');
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'light',
      setTheme: () => {
        applyLight();
        set({ theme: 'light' });
      },
    }),
    {
      name: 'llamatrade-theme',
      onRehydrateStorage: () => () => {
        applyLight();
      },
    }
  )
);

if (typeof window !== 'undefined') {
  applyLight();
}
