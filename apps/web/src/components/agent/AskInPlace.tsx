/**
 * Copilot on other pages (panel2 A): an ask field for the page header and an answer block the
 * page places under the panels it is about. Both share the Copilot thread, so Continue in
 * Copilot carries it to the full page.
 */

import { MessageRole, useAgentStore } from '@llamatrade/core/stores/agent';
import { ArrowUpRight, Sparkles, X } from 'lucide-react';
import { useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { Kbd } from '../ui';

import { useInlineAsk } from './inlineAsk';
import { threadSources } from './sources';
import { CitationMark } from './SourcesPane';
import { StreamingIndicator } from './StreamingIndicator';
import { askPlaceholder, type CopilotSubject } from './subjects';
import { useCopilotSubject } from './subjectStore';
import { useCopilotSend } from './useCopilotSend';

/** The ask field for a page header; the answer appears in `CopilotInlineAnswer`. */
export function CopilotAskField({
  subject,
  page,
  placeholder,
}: {
  subject: CopilotSubject | null;
  page: string;
  placeholder?: string;
}) {
  const [value, setValue] = useState('');
  const startNewChat = useAgentStore((s) => s.startNewChat);
  const busy = useAgentStore((s) => s.isStreaming);
  const open = useInlineAsk((s) => s.open);
  const send = useCopilotSend(page);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    if (!q || busy) return;
    startNewChat();
    useCopilotSubject.getState().setSubject(subject);
    open(q);
    setValue('');
    send(q);
  };

  const label = placeholder ?? (subject ? askPlaceholder(subject) : 'Ask Copilot');
  return (
    <form
      onSubmit={submit}
      className="hidden h-10 w-[340px] items-center gap-2 rounded-full border border-line-strong bg-panel px-4 focus-within:border-accent md:flex"
    >
      <Sparkles className="h-4 w-4 flex-none text-accent" />
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label={label}
        placeholder={label}
        className="min-w-0 flex-1 bg-transparent text-[13.5px] text-fg outline-none placeholder:text-fg-2"
      />
      <Kbd>⌘J</Kbd>
    </form>
  );
}

/** The answer to a question asked from the page header, as a block inside the page. */
export function CopilotInlineAnswer({ scopeNote }: { scopeNote?: string }) {
  const navigate = useNavigate();
  const question = useInlineAsk((s) => s.question);
  const close = useInlineAsk((s) => s.close);
  const { messages, isStreaming, streamingContent, currentSessionId, serviceUnavailable } =
    useAgentStore();
  const sources = useMemo(() => threadSources(messages), [messages]);
  const answer = [...messages].reverse().find((m) => m.role !== MessageRole.USER);

  if (!question) return null;

  const cont = () => {
    close();
    navigate(currentSessionId ? `/copilot/${currentSessionId}` : '/copilot');
  };

  return (
    <section
      aria-label={question}
      className="panel overflow-hidden border-accent/50 shadow-[0_0_0_3px_var(--accent-soft)]"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-3">
        <Sparkles className="h-4 w-4 flex-none text-accent" />
        <b className="min-w-0 text-[14px] font-semibold">{question}</b>
        <span className="text-[12px] text-fg-3">Copilot{scopeNote ? ` · ${scopeNote}` : ''}</span>
        <span className="ml-auto flex items-center gap-1">
          <button type="button" className="btn btn-ghost btn-sm" onClick={cont}>
            Continue in Copilot
            <ArrowUpRight className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm px-1.5"
            aria-label="Close the answer"
            onClick={close}
          >
            <X className="h-4 w-4" />
          </button>
        </span>
      </div>
      <div className="grid gap-5 px-4 py-4 md:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 whitespace-pre-wrap text-[14px] leading-[1.6]">
          {serviceUnavailable ? (
            <span className="text-fg-2">
              Copilot is unavailable, so nothing was sent. The rest of this page works as usual.
            </span>
          ) : isStreaming ? (
            <StreamingIndicator content={streamingContent} />
          ) : (
            (answer?.content ?? '')
          )}
        </div>
        {sources.length > 0 && (
          <ol className="m-0 grid list-none content-start gap-0 p-0">
            {sources.map((s) => (
              <li
                key={`${s.n}-${s.id}`}
                className="flex items-center gap-2.5 border-b border-line py-2 text-[13px] last:border-0"
              >
                <CitationMark n={s.n} />
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
