import { useEffect } from 'react';
import { create } from 'zustand';

interface PaletteState {
  open: boolean;
  show: () => void;
  hide: () => void;
  toggle: () => void;
}

export const usePalette = create<PaletteState>((set) => ({
  open: false,
  show: () => set({ open: true }),
  hide: () => set({ open: false }),
  toggle: () => set((s) => ({ open: !s.open })),
}));

/** Opens the palette with Cmd+K or Ctrl+K anywhere in the app. */
export function useCommandPaletteShortcut() {
  const toggle = usePalette((s) => s.toggle);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        toggle();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [toggle]);
}
