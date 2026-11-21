import { fromDSLString, validateTree } from '@llamatrade/core/strategy/serializer';
import { create } from 'zustand';

export interface Draft {
  code: string;
  /** The version the draft started from; 0 for a new strategy. */
  baseVersion: number;
}

interface DraftState {
  drafts: Record<string, Draft>;
  setDraft: (id: string, draft: Draft) => void;
  discard: (id: string) => void;
}

/** Unsaved edits, kept in memory for as long as the app runs; the server only sees saved versions. */
export const useDrafts = create<DraftState>((set) => ({
  drafts: {},
  setDraft: (id, draft) => set((s) => ({ drafts: { ...s.drafts, [id]: draft } })),
  discard: (id) =>
    set((s) => {
      const next = { ...s.drafts };
      delete next[id];
      return { drafts: next };
    }),
}));

export interface Problems {
  errors: string[];
  warnings: string[];
}

/** The same structural checks the web builder runs before a save. */
export function checkCode(code: string): Problems {
  const parsed = fromDSLString(code);
  if (!parsed) return { errors: ['The strategy code could not be read.'], warnings: [] };
  const result = validateTree(parsed.tree);
  return { errors: result.errors.map((e) => e.message), warnings: result.warnings.map((w) => w.message) };
}
