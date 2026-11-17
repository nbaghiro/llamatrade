import { describeConfirmation, type ConfirmationView } from '@llamatrade/core/agent/confirmation';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useAgentStore, type PendingConfirmation } from '@llamatrade/core/stores/agent';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useEffect, useMemo } from 'react';

/** A proposed action read into its title, labelled arguments and plain effect, with names for ids. */
export function useConfirmationView(
  confirmation: PendingConfirmation,
  loadNames = true
): ConfirmationView {
  const artifacts = useAgentStore((s) => s.pendingArtifacts);
  const strategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const namesStrategy = confirmation.argumentsJson.includes('"strategy_id"');

  useEffect(() => {
    if (loadNames && namesStrategy && strategies.length === 0) fetchStrategies();
  }, [loadNames, namesStrategy, strategies.length, fetchStrategies]);

  return useMemo(() => {
    const names: Record<string, string> = {};
    for (const st of strategies) {
      names[st.id] = st.status === StrategyStatus.DRAFT ? `${st.name} (draft)` : st.name;
    }
    for (const a of artifacts) {
      if (a.committedResourceId) names[a.committedResourceId] = `${a.name} (draft)`;
    }
    return describeConfirmation(confirmation.toolName, confirmation.argumentsJson, names);
  }, [confirmation, artifacts, strategies]);
}
