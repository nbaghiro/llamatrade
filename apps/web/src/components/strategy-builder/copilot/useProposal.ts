import { ArtifactType, type PendingArtifact } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo } from 'react';

import { diffStrategies, type StrategyDiff } from '../../../lib/strategyDiff';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';

import { backtestEvidence, proposalDsl, type EvidenceRun } from './evidence';

export interface Proposal {
  artifact: PendingArtifact;
  dsl: string;
  diff: StrategyDiff;
  evidence: EvidenceRun[];
}

/** The latest strategy change Copilot proposed in this conversation, compared with the draft. */
export function useProposal(): Proposal | null {
  const { tree, timeframe, benchmark } = useStrategyBuilderStoreWithContext();
  const pendingArtifacts = useAgentStore((s) => s.pendingArtifacts);
  const messages = useAgentStore((s) => s.messages);
  const sessionId = useAgentStore((s) => s.currentSessionId);

  return useMemo(() => {
    const artifact = [...pendingArtifacts]
      .reverse()
      .find(
        (a) =>
          a.artifactType === ArtifactType.STRATEGY &&
          !a.isCommitted &&
          (!sessionId || a.sessionId === sessionId)
      );
    if (!artifact) return null;
    const dsl = proposalDsl(artifact.previewJson);
    const parsed = dsl ? fromDSLString(dsl) : null;
    if (!dsl || !parsed) return null;
    const diff = diffStrategies(
      { tree, meta: { timeframe, benchmark } },
      {
        tree: parsed.tree,
        meta: {
          timeframe: parsed.metadata.timeframe ?? timeframe,
          benchmark: parsed.metadata.benchmark ?? '',
        },
      }
    );
    const evidence = backtestEvidence(messages.flatMap((m) => m.toolCalls));
    return { artifact, dsl, diff, evidence };
  }, [pendingArtifacts, messages, sessionId, tree, timeframe, benchmark]);
}
