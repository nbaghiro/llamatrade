/**
 * UI Store
 * Global UI state for dialogs, modals, and other transient UI elements.
 */

import { create } from 'zustand';

import type { StrategyTemplate } from '../data/strategy-templates';

interface UIState {
  // New Strategy Dialog
  newStrategyDialogOpen: boolean;
  openNewStrategyDialog: () => void;
  closeNewStrategyDialog: () => void;

  // Strategy Preview Dialog
  previewDialogOpen: boolean;
  previewTemplate: StrategyTemplate | null;
  openPreviewDialog: (template: StrategyTemplate) => void;
  closePreviewDialog: () => void;
  closeAllStrategyDialogs: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  // New Strategy Dialog
  newStrategyDialogOpen: false,
  openNewStrategyDialog: () => set({ newStrategyDialogOpen: true }),
  closeNewStrategyDialog: () => set({ newStrategyDialogOpen: false }),

  // Strategy Preview Dialog
  previewDialogOpen: false,
  previewTemplate: null,
  openPreviewDialog: (template: StrategyTemplate) =>
    set({ previewDialogOpen: true, previewTemplate: template }),
  closePreviewDialog: () =>
    set({ previewDialogOpen: false, previewTemplate: null }),
  closeAllStrategyDialogs: () =>
    set({
      newStrategyDialogOpen: false,
      previewDialogOpen: false,
      previewTemplate: null,
    }),
}));
