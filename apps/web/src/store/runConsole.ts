/**
 * Run Console overlay control — a single global "run a backtest" modal opened from
 * anywhere a strategy is shown (list row, builder, detail drawer), instead of deep-linking
 * to the backtest page. The run itself lives in the shared backtest store.
 */

import { create } from 'zustand';

interface RunConsoleState {
  open: boolean;
  strategyId: string | null;
  strategyName: string;
  /** Omit args to open blank — the console then offers a strategy picker. */
  openRunConsole: (strategyId?: string, strategyName?: string) => void;
  closeRunConsole: () => void;
}

export const useRunConsole = create<RunConsoleState>((set) => ({
  open: false,
  strategyId: null,
  strategyName: '',
  openRunConsole: (strategyId, strategyName = '') =>
    set({ open: true, strategyId: strategyId ?? null, strategyName }),
  closeRunConsole: () => set({ open: false }),
}));
