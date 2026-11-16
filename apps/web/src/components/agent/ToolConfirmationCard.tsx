import { describeConfirmation } from '@llamatrade/core/agent/confirmation';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import {
  useAgentStore,
  type ConfirmationDecision,
  type PendingConfirmation,
} from '@llamatrade/core/stores/agent';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { Play } from 'lucide-react';
import { useEffect, useMemo } from 'react';

import { Pill } from '../ui';

interface ToolConfirmationCardProps {
  confirmation: PendingConfirmation;
  /** Set once answered; the card then stays in the thread as a record. */
  decision?: ConfirmationDecision;
}

const DECISION_LABEL: Record<ConfirmationDecision, string> = {
  approved: 'Approved',
  declined: 'Declined',
  change: 'You asked for changes',
};

/** A proposed action in the thread: its exact arguments, what it will and won't do, and the answer. */
export function ToolConfirmationCard({ confirmation, decision }: ToolConfirmationCardProps) {
  const confirmToolCall = useAgentStore((s) => s.confirmToolCall);
  const isStreaming = useAgentStore((s) => s.isStreaming);
  const artifacts = useAgentStore((s) => s.pendingArtifacts);
  const strategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const pending = decision === undefined;
  const namesStrategy = confirmation.argumentsJson.includes('"strategy_id"');

  useEffect(() => {
    if (pending && namesStrategy && strategies.length === 0) fetchStrategies();
  }, [pending, namesStrategy, strategies.length, fetchStrategies]);

  const view = useMemo(() => {
    const names: Record<string, string> = {};
    for (const st of strategies) {
      names[st.id] = st.status === StrategyStatus.DRAFT ? `${st.name} (draft)` : st.name;
    }
    for (const a of artifacts) {
      if (a.committedResourceId) names[a.committedResourceId] = `${a.name} (draft)`;
    }
    return describeConfirmation(confirmation.toolName, confirmation.argumentsJson, names);
  }, [confirmation, artifacts, strategies]);

  return (
    <section
      aria-label={view.title}
      className={`min-w-0 overflow-hidden rounded-panel border bg-panel ${
        pending ? 'border-accent/55 shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line-strong'
      }`}
    >
      <div className="flex items-center justify-between gap-2.5 border-b border-line px-3.5 py-[11px]">
        <b className="font-semibold">{view.title}</b>
        {pending ? (
          <Pill tone="accent">Needs your approval</Pill>
        ) : (
          <Pill>{DECISION_LABEL[decision]}</Pill>
        )}
      </div>
      <div className="grid gap-3 px-3.5 py-3">
        {view.args.length > 0 && (
          <dl className="m-0 grid grid-cols-[96px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[13px]">
            {view.args.map((a, i) => (
              <div key={`${a.label}-${i}`} className="contents">
                <dt className="text-fg-3">{a.label}</dt>
                <dd className="m-0 break-words font-mono text-[12.5px]">{a.value}</dd>
              </div>
            ))}
          </dl>
        )}
        <span className="text-[12.5px] text-fg-3">{view.effect}</span>
      </div>
      {pending && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-sunk px-3.5 py-2.5">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => confirmToolCall(true)}
            disabled={isStreaming}
          >
            <Play className="h-3.5 w-3.5" />
            Approve and run
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => confirmToolCall(false, 'change')}
            disabled={isStreaming}
          >
            Change settings
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => confirmToolCall(false)}
            disabled={isStreaming}
          >
            Decline
          </button>
        </div>
      )}
    </section>
  );
}
