import { createContext, useContext } from 'react';

export type ProposalState = 'open' | 'applied' | 'dismissed';

export interface AskApi {
  ask: (prompt: string, context?: string) => void;
  openSheet: () => void;
  register: (el: HTMLElement | null) => void;
  proposals: Record<string, ProposalState>;
  setProposal: (id: string, s: ProposalState) => void;
}

export const AskContext = createContext<AskApi | null>(null);

export function useAsk(): AskApi {
  const v = useContext(AskContext);
  if (!v) throw new Error('useAsk outside AskProvider');
  return v;
}
