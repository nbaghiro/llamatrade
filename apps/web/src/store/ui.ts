/**
 * UI Store
 * Global UI state for dialogs, modals, and other transient UI elements.
 */

import { create } from 'zustand';

interface UIState {
  // New Strategy Dialog
  newStrategyDialogOpen: boolean;
  openNewStrategyDialog: () => void;
  closeNewStrategyDialog: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  // New Strategy Dialog
  newStrategyDialogOpen: false,
  openNewStrategyDialog: () => set({ newStrategyDialogOpen: true }),
  closeNewStrategyDialog: () => set({ newStrategyDialogOpen: false }),
}));
