import { sessionWhen } from '@llamatrade/core/agent/history';
import type { AgentSession } from '@llamatrade/core/stores/agent';
import { Link } from 'react-router-dom';

import { ChatInput } from '../../components/agent/ChatInput';
import { conversationPath } from '../../components/agent/entry';
import type { StarterGroup } from '../../components/agent/subjects';
import { CopilotMark } from '../../components/common/Logo';

const ORDER: readonly StarterGroup['label'][] = ['Explain', 'Test', 'Build'];

/** Home: the Copilot mark, a heading, a large composer and three suggestions under it. */
export function OpenCanvas({
  starters,
  last,
  onSend,
  onDraft,
  disabled,
  busy,
  initialValue = '',
}: {
  starters: StarterGroup[];
  last: AgentSession | null;
  onSend: (text: string) => void;
  /** Sends a strategy description so Copilot asks its questions first. */
  onDraft: (text: string) => void;
  disabled: boolean;
  busy: boolean;
  initialValue?: string;
}) {
  const chips = ORDER.flatMap((label) => {
    const group = starters.find((g) => g.label === label);
    const prompt = group?.prompts[0];
    return prompt ? [{ label, prompt }] : [];
  });

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 pb-16 pt-[9vh] md:pt-[14vh]">
      <div className="mx-auto grid max-w-[680px] justify-items-center text-center motion-safe:animate-rise">
        <CopilotMark size={34} className="text-fg" />
        <h1 className="m-0 mb-7 mt-4 text-[26px] font-semibold tracking-[-0.035em] md:text-[30px]">
          What should your strategy do?
        </h1>
        <div className="w-full text-left">
          <ChatInput
            large
            autoFocus
            onSend={onSend}
            initialValue={initialValue}
            disabled={disabled}
            busy={busy}
            placeholder="Describe a strategy, or ask about one you run"
            hint="Copilot drafts it. Nothing trades until you start a session."
          />
        </div>
        {chips.length > 0 && (
          <div className="mt-[18px] flex flex-wrap justify-center gap-2">
            {chips.map(({ label, prompt }) => (
              <button
                key={prompt}
                type="button"
                disabled={disabled || busy}
                onClick={() => (label === 'Build' ? onDraft(prompt) : onSend(prompt))}
                className="rounded-full border border-line-strong px-3 py-[5px] text-[12.5px] text-fg-2 transition-colors hover:border-fg-3 hover:text-fg disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
        {last && (
          <p className="m-0 mt-10 text-[12.5px] text-fg-3">
            Last conversation:{' '}
            <Link
              to={conversationPath(last.id)}
              className="text-fg-2 hover:text-fg hover:underline"
            >
              {last.title || 'Untitled'}
            </Link>
            , {sessionWhen(last.lastActivityAt?.seconds)}
          </p>
        )}
      </div>
    </div>
  );
}
