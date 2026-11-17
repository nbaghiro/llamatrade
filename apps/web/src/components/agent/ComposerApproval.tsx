import { useAgentStore, type PendingConfirmation } from '@llamatrade/core/stores/agent';
import { LineChart } from 'lucide-react';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';

import { Kbd } from '../ui';

import { changedArgs, changeMessage } from './approval';
import { useConfirmationView } from './useConfirmationView';

/**
 * While Copilot waits for an answer, the composer becomes the approval (approval B). Enter
 * approves, Escape declines. Copilot runs only the arguments it proposed, so a changed value
 * declines this run and puts a message asking for the new values in the composer.
 */
export function ComposerApproval({ confirmation }: { confirmation: PendingConfirmation }) {
  const confirmToolCall = useAgentStore((s) => s.confirmToolCall);
  const isStreaming = useAgentStore((s) => s.isStreaming);
  const view = useConfirmationView(confirmation);
  const [edited, setEdited] = useState<string[]>([]);
  const root = useRef<HTMLDivElement>(null);
  const ids = useId();

  useEffect(() => {
    setEdited(view.args.map((a) => a.value));
  }, [view.args]);

  useEffect(() => {
    root.current?.querySelector<HTMLElement>('[data-approve]')?.focus();
  }, [confirmation.confirmationId]);

  const changes = changedArgs(view.args, edited);
  const changed = changes.length > 0;
  const title = view.title.charAt(0).toLowerCase() + view.title.slice(1);

  const approve = () => {
    if (isStreaming) return;
    if (!changed) {
      confirmToolCall(true);
      return;
    }
    confirmToolCall(false, 'change');
    useAgentStore.setState({ seedPrompt: changeMessage(changes) });
  };
  const decline = () => {
    if (!isStreaming) confirmToolCall(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      decline();
    } else if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      approve();
    }
  };

  return (
    <div
      ref={root}
      role="group"
      aria-label={`Copilot asks to ${title}`}
      onKeyDown={onKeyDown}
      className="overflow-hidden rounded-[12px] border border-accent/55 bg-panel shadow-[0_0_0_3px_var(--accent-soft)]"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 pb-2 pt-3">
        <b className="flex items-center gap-2 text-[14px] font-semibold">
          <LineChart className="h-4 w-4 flex-none text-accent" />
          Copilot asks to {title}
        </b>
        <span className="text-[12px] text-fg-3">{view.effect}</span>
      </div>
      {view.args.length > 0 && (
        <div className="grid grid-cols-2 gap-3 px-4 pb-3 sm:grid-cols-[repeat(auto-fit,minmax(130px,1fr))]">
          {view.args.map((a, i) => {
            const id = `${ids}-${i}`;
            const readOnly = a.label === 'Strategy';
            return (
              <label
                key={`${a.label}-${i}`}
                htmlFor={id}
                className={`grid min-w-0 gap-1 ${readOnly ? 'col-span-2 sm:col-span-1' : ''}`}
              >
                <span className="text-[12.5px] text-fg-2">{a.label}</span>
                <input
                  id={id}
                  value={edited[i] ?? a.value}
                  readOnly={readOnly}
                  onChange={(e) =>
                    setEdited((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))
                  }
                  className={`h-9 min-w-0 rounded-[7px] border px-2.5 font-mono text-[13px] outline-none focus:border-accent ${
                    readOnly
                      ? 'truncate border-line bg-sunk font-sans text-fg-2'
                      : 'border-line-strong bg-panel text-fg'
                  }`}
                />
              </label>
            );
          })}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-sunk px-4 py-2.5">
        <button
          type="button"
          data-approve
          className="btn btn-primary"
          onClick={approve}
          disabled={isStreaming}
        >
          {changed ? 'Ask for these values' : 'Approve and run'}
          <Kbd>↵</Kbd>
        </button>
        <button type="button" className="btn btn-ghost" onClick={decline} disabled={isStreaming}>
          Decline
          <Kbd>Esc</Kbd>
        </button>
        <span className="ml-auto text-[12px] text-fg-3">
          {changed
            ? 'Copilot proposes the run again with your values.'
            : 'Copilot never places orders.'}
        </span>
      </div>
    </div>
  );
}
