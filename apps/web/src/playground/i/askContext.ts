import { createContext, useContext } from 'react';

export type ProposalState = 'open' | 'applied' | 'dismissed';
export type Artifact = 'today' | 'proposal' | 'draft' | 'explain';

export interface Turn {
  id: number;
  role: 'you' | 'copilot';
  text: string;
  artifact?: Artifact;
  strategyId?: string;
}

export interface AskApi {
  turns: Turn[];
  /** Characters of the newest Copilot reply shown so far, while it streams. */
  shown: number;
  ask: (prompt: string, context?: string) => void;
  /** True while the card shows the conversation in place of the page. */
  open: boolean;
  setOpen: (open: boolean) => void;
  proposals: Record<string, ProposalState>;
  setProposal: (id: string, s: ProposalState) => void;
}

export const AskContext = createContext<AskApi | null>(null);

export function useAsk(): AskApi {
  const v = useContext(AskContext);
  if (!v) throw new Error('useAsk outside AskProvider');
  return v;
}
