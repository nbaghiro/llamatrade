import type { ConfirmationDecision, PendingConfirmation } from '@llamatrade/core/stores/agent';
import { Check, X } from 'lucide-react';

import { approvalRecord } from './approval';
import { useConfirmationView } from './useConfirmationView';

/** An answered proposal, written back into the thread as one line. */
export function ToolConfirmationCard({
  confirmation,
  decision,
}: {
  confirmation: PendingConfirmation;
  decision: ConfirmationDecision;
}) {
  const view = useConfirmationView(confirmation, false);
  const approved = decision === 'approved';
  return (
    <div className="flex min-w-0 items-center gap-2 justify-self-start text-[12.5px] text-fg-3">
      {approved ? (
        <Check className="h-3.5 w-3.5 flex-none text-accent" />
      ) : (
        <X className="h-3.5 w-3.5 flex-none" />
      )}
      <span className="min-w-0 truncate">{approvalRecord(view.title, decision, view.args)}</span>
    </div>
  );
}
