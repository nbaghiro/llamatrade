/** Inline approval card for a write action the agent has proposed (draft + confirm). */

import { useAgentStore } from '@llamatrade/core/stores/agent';
import { Check, Play, X } from 'lucide-react';
import { useMemo } from 'react';


/** Human labels for confirmation-gated tools; falls back to the de-underscored name. */
const TOOL_LABELS: Record<string, string> = {
  run_backtest: 'Run a backtest',
};

function humanizeTool(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, ' ');
}

function summarizeArgs(argumentsJson: string): Array<[string, string]> {
  try {
    const args = JSON.parse(argumentsJson) as Record<string, unknown>;
    return Object.entries(args)
      .filter(([, v]) => v !== '' && v != null)
      .map(([k, v]) => [k.replace(/_/g, ' '), String(v)]);
  } catch {
    return [];
  }
}

export function ToolConfirmationCard() {
  const pending = useAgentStore((s) => s.pendingConfirmation);
  const confirmToolCall = useAgentStore((s) => s.confirmToolCall);
  const isStreaming = useAgentStore((s) => s.isStreaming);

  const args = useMemo(() => (pending ? summarizeArgs(pending.argumentsJson) : []), [pending]);

  if (!pending) return null;

  return (
    <div className="pl-[50px]">
      <div className="w-full min-w-0 max-w-full border-2 border-orange-500 bg-paper shadow-[4px_4px_0_rgb(var(--lt-ink))]">
        <div className="flex items-center gap-2 border-b-2 border-ink bg-orange-500/15 px-3.5 py-2.5">
          <Play className="h-3.5 w-3.5 text-orange-600" />
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-ink/60">
            Approve action
          </span>
          <span className="text-sm font-black tracking-tight text-ink">
            {humanizeTool(pending.toolName)}
          </span>
        </div>

        {args.length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 px-3.5 py-2.5 font-mono text-[11px] text-ink/70">
            {args.map(([k, v]) => (
              <span key={k}>
                <span className="uppercase tracking-[0.04em] text-ink/45">{k}:</span> {v}
              </span>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2.5 border-t-2 border-ink px-3.5 py-3">
          <button
            onClick={() => confirmToolCall(true)}
            disabled={isStreaming}
            className="flex items-center gap-1.5 border-2 border-ink bg-orange-500 px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.04em] text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-all hover:bg-orange-600 disabled:opacity-40 disabled:shadow-none"
          >
            <Check className="h-3.5 w-3.5" />
            Approve &amp; run
          </button>
          <button
            onClick={() => confirmToolCall(false)}
            disabled={isStreaming}
            className="flex items-center gap-1.5 border-2 border-ink bg-paper px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.04em] text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-all hover:bg-bone disabled:opacity-40 disabled:shadow-none"
          >
            <X className="h-3.5 w-3.5" />
            Decline
          </button>
        </div>
      </div>
    </div>
  );
}
