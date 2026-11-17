import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { create } from 'zustand';

import type { CopilotSubject } from './subjects';

interface SubjectState {
  /** What the current question is about; shown as a chip in the composer. */
  subject: CopilotSubject | null;
  /** A question kept because Copilot couldn't be reached when it was sent. */
  unsent: { text: string; at: Date } | null;
  setSubject: (subject: CopilotSubject | null) => void;
  setUnsent: (text: string | null) => void;
}

export const useCopilotSubject = create<SubjectState>()((set) => ({
  subject: null,
  unsent: null,
  setSubject: (subject) => set({ subject }),
  setUnsent: (text) => set({ unsent: text ? { text, at: new Date() } : null }),
}));

/** The strategy name and code Copilot is given as context for a subject. */
export function subjectContext(subject: CopilotSubject | null): { name?: string; dsl?: string } {
  if (!subject?.strategyId) return {};
  const { strategies, details } = useStrategiesStore.getState();
  const strategy =
    details[subject.strategyId] ?? strategies.find((s) => s.id === subject.strategyId);
  return { name: subject.strategyName ?? strategy?.name, dsl: strategy?.dslCode || undefined };
}
