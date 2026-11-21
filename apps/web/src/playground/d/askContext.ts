import { createContext, useContext } from 'react';

export type ProposalState = 'open' | 'applied' | 'dismissed';

export type Artifact =
  | 'today'
  | 'proposal'
  | 'draft'
  | 'explain'
  | 'drift'
  | 'session'
  | 'classes'
  | 'fills';

export interface Turn {
  id: number;
  q: string;
  text: string;
  at: string;
  born: number;
  artifact?: Artifact;
  strategyId?: string;
  sessionId?: string;
}

export interface AskApi {
  scope: string;
  thread: Turn[];
  ask: (prompt: string, context?: string) => void;
  remove: (id: number) => void;
  clear: () => void;
  focusComposer: () => void;
  register: (el: HTMLInputElement | null) => void;
  proposals: Record<string, ProposalState>;
  setProposal: (id: string, s: ProposalState) => void;
}

export const AskContext = createContext<AskApi | null>(null);

export function useAsk(): AskApi {
  const v = useContext(AskContext);
  if (!v) throw new Error('useAsk outside AskProvider');
  return v;
}
