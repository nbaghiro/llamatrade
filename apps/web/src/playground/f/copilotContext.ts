import { createContext, useContext } from 'react';

export type ProposalState = 'open' | 'applied' | 'dismissed';
export type Artifact = 'today' | 'proposal' | 'draft' | 'explain' | 'backtest';

export interface Turn {
  id: number;
  role: 'you' | 'copilot';
  text: string;
  artifact?: Artifact;
  strategyId?: string;
  years?: number;
}

export type Action =
  | { type: 'go'; to: string }
  | { type: 'ask'; prompt: string; context?: string }
  | { type: 'backtest'; strategyId: string; years: number };

export interface CopilotApi {
  turns: Turn[];
  streamId: number | null;
  doneStreaming: () => void;
  run: (action: Action) => void;
  /** Runs the best match for free text: a command, a jump or a question. */
  submit: (query: string, context?: string) => void;
  openBar: (context?: string) => void;
  closeBar: () => void;
  proposals: Record<string, ProposalState>;
  setProposal: (id: string, s: ProposalState) => void;
}

export const CopilotContext = createContext<CopilotApi | null>(null);

export function useCopilot(): CopilotApi {
  const v = useContext(CopilotContext);
  if (!v) throw new Error('useCopilot outside CopilotProvider');
  return v;
}
