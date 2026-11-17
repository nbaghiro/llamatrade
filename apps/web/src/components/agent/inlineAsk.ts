import { create } from 'zustand';

interface InlineAskState {
  question: string | null;
  open: (question: string) => void;
  close: () => void;
}

export const useInlineAsk = create<InlineAskState>()((set) => ({
  question: null,
  open: (question) => set({ question }),
  close: () => set({ question: null }),
}));
