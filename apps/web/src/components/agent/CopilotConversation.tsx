/** The Copilot thread in a centred column, with the composer pinned under it. */

import {
  MessageRole,
  useAgentStore,
  type ResolvedConfirmation,
} from '@llamatrade/core/stores/agent';
import { Activity, AlertTriangle, Clock } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { ChatInput, SubjectChip } from './ChatInput';
import { ChatMessage, UserBubble } from './ChatMessage';
import { ComposerApproval } from './ComposerApproval';
import { stripDraftInstruction } from './draftQuestions';
import { followUpsFor } from './followUps';
import { copilotLimit, limitCopy, type CopilotLimit } from './limits';
import { PendingArtifactCard } from './PendingArtifactCard';
import { threadSources, type SourceView } from './sources';
import { StreamingIndicator } from './StreamingIndicator';
import { useCopilotSubject } from './subjectStore';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallIndicator } from './ToolCallIndicator';
import { ToolConfirmationCard } from './ToolConfirmationCard';
import { useCopilotSend } from './useCopilotSend';

const COLUMN = 'mx-auto w-full max-w-[720px] px-4 md:px-6';
const FOOTER_NOTE = 'Copilot proposes, you confirm';

/** Copilot can't take a message: the notice that stands where the composer was (limits A). */
function LimitNotice({ limit, onRetry }: { limit: CopilotLimit; onRetry: (text: string) => void }) {
  const unsent = useCopilotSubject((s) => s.unsent);
  const downSince = useCopilotSubject((s) => s.downSince);
  const setUnsent = useCopilotSubject((s) => s.setUnsent);
  const loadSessions = useAgentStore((s) => s.loadSessions);
  const copy = limitCopy(limit, downSince, unsent !== null);

  const edit = () => {
    if (!unsent) return;
    const { messages } = useAgentStore.getState();
    const last = messages[messages.length - 1];
    const failed =
      last?.role === MessageRole.USER &&
      last.id.startsWith('temp-') &&
      last.content === unsent.text;
    useAgentStore.setState({
      seedPrompt: stripDraftInstruction(unsent.text),
      serviceUnavailable: false,
      error: null,
      ...(failed ? { messages: messages.slice(0, -1) } : {}),
    });
    setUnsent(null);
  };

  return (
    <div
      role="status"
      className="grid gap-2.5 rounded-[14px] border border-line bg-panel px-4 py-3.5 shadow-[0_8px_30px_-16px_rgb(0_0_0/0.25)] md:px-[18px] md:py-4"
    >
      <div className="flex items-center gap-2">
        {limit === 'rate' ? (
          <Clock className="h-4 w-4 flex-none text-risk" aria-hidden="true" />
        ) : (
          <AlertTriangle className="h-4 w-4 flex-none text-risk" aria-hidden="true" />
        )}
        <b className="text-[13.5px] font-semibold">{copy.title}</b>
      </div>
      <p className="m-0 text-[13px] leading-[1.55] text-fg-2">{copy.body}</p>
      <div className="flex flex-wrap items-center gap-2">
        {unsent ? (
          <>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onRetry(unsent.text)}
            >
              Try again
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={edit}>
              Edit
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              useAgentStore.setState({ error: null });
              loadSessions();
            }}
          >
            Check again
          </button>
        )}
        <span className="flex-1" />
        <Link to="/strategies/builder" className="btn btn-ghost btn-sm max-md:hidden">
          Open the builder
        </Link>
        <Link to="/backtest" className="btn btn-ghost btn-sm max-md:hidden">
          Run a backtest
        </Link>
      </div>
    </div>
  );
}

export function CopilotConversation({ page }: { page: string }) {
  const {
    messages,
    pendingArtifacts,
    pendingArtifactIdsForCurrentMessage,
    isStreaming,
    streamingContent,
    thinkingContent,
    currentToolCall,
    pendingConfirmation,
    resolvedConfirmations,
    seedPrompt,
    serviceUnavailable,
    loading,
    error,
    clearError,
    clearSeedPrompt,
    loadSessions,
  } = useAgentStore();
  const subject = useCopilotSubject((s) => s.subject);
  const setSubject = useCopilotSubject((s) => s.setSubject);
  const unsent = useCopilotSubject((s) => s.unsent);
  const downSince = useCopilotSubject((s) => s.downSince);
  const setDownSince = useCopilotSubject((s) => s.setDownSince);
  const send = useCopilotSend(page);

  const scroller = useRef<HTMLDivElement>(null);
  const wasStreaming = useRef(false);
  const [draft, setDraft] = useState({ text: '', key: 0 });
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const limit = copilotLimit({ serviceUnavailable, error });

  useEffect(() => {
    if (limit && !downSince) setDownSince(new Date());
    if (!limit && downSince) setDownSince(null);
  }, [limit, downSince, setDownSince]);

  useEffect(() => {
    if (!seedPrompt) return;
    setDraft((d) => ({ text: seedPrompt, key: d.key + 1 }));
    clearSeedPrompt();
  }, [seedPrompt, clearSeedPrompt]);

  useEffect(() => {
    if (wasStreaming.current && !isStreaming) loadSessions();
    wasStreaming.current = isStreaming;
  }, [isStreaming, loadSessions]);

  useEffect(() => {
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const el = scroller.current;
    el?.scrollTo({ top: el.scrollHeight, behavior: still ? 'auto' : 'smooth' });
  }, [
    messages,
    streamingContent,
    thinkingContent,
    currentToolCall,
    pendingArtifacts.length,
    pendingConfirmation,
  ]);

  const artifactMap = useMemo(
    () => new Map(pendingArtifacts.map((a) => [a.id, a] as const)),
    [pendingArtifacts]
  );

  const sources = useMemo(() => threadSources(messages), [messages]);
  const firstSource = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of sources) if (!map.has(s.messageId)) map.set(s.messageId, s.n);
    return map;
  }, [sources]);
  const sourcesOf = useMemo(() => {
    const map = new Map<string, SourceView[]>();
    for (const s of sources) map.set(s.messageId, [...(map.get(s.messageId) ?? []), s]);
    return map;
  }, [sources]);

  const unlinked = useMemo(() => {
    const linked = new Set<string>();
    for (const m of messages) for (const id of m.inlineArtifactIds ?? []) linked.add(id);
    const inFlight = new Set(pendingArtifactIdsForCurrentMessage);
    return pendingArtifacts.filter((a) => !linked.has(a.id) && !inFlight.has(a.id));
  }, [messages, pendingArtifacts, pendingArtifactIdsForCurrentMessage]);

  const answeredAfter = useMemo(() => {
    const map = new Map<string | null, ResolvedConfirmation[]>();
    for (const r of resolvedConfirmations) {
      map.set(r.afterMessageId, [...(map.get(r.afterMessageId) ?? []), r]);
    }
    return map;
  }, [resolvedConfirmations]);

  const answered = (after: string | null) =>
    answeredAfter
      .get(after)
      ?.map((r) => (
        <ToolConfirmationCard key={r.confirmationId} confirmation={r} decision={r.decision} />
      ));

  const last = messages[messages.length - 1];
  const failedLast =
    unsent !== null &&
    last?.role === MessageRole.USER &&
    last.id.startsWith('temp-') &&
    last.content === unsent.text;
  const lastAnswer = [...messages].reverse().find((m) => m.role !== MessageRole.USER);
  const followUps = isStreaming || limit ? [] : followUpsFor(subject, messages);

  return (
    <>
      <div ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div className={`${COLUMN} pb-10 pt-14`}>
          {loading && messages.length === 0 ? (
            <div className="grid gap-5" aria-busy="true">
              <span className="sr-only" role="status">
                Loading the conversation
              </span>
              <div className="ml-auto h-10 w-1/2 rounded-[14px] bg-sunk motion-safe:animate-pulse" />
              <div className="grid gap-2">
                <div className="h-3 w-24 rounded bg-sunk motion-safe:animate-pulse" />
                <div className="h-4 w-full rounded bg-sunk motion-safe:animate-pulse" />
                <div className="h-4 w-5/6 rounded bg-sunk motion-safe:animate-pulse" />
              </div>
            </div>
          ) : (
            <div className="grid gap-7">
              {answered(null)}
              {messages.map((m, i) => (
                <div key={m.id} className="grid gap-5">
                  <ChatMessage
                    message={m}
                    artifacts={artifactMap}
                    firstSource={firstSource.get(m.id)}
                    activeSource={activeSource}
                    onCite={setActiveSource}
                    sources={sourcesOf.get(m.id)}
                    followUps={m === lastAnswer && i === messages.length - 1 ? followUps : []}
                    onAsk={(q) => send(q)}
                    onReply={
                      isStreaming || limit ? undefined : (text) => send(text, { draft: false })
                    }
                    replied={i < messages.length - 1}
                    notSent={failedLast && m === last}
                  />
                  {answered(m.id)}
                </div>
              ))}
              {unsent && !failedLast && <UserBubble text={unsent.text} notSent />}

              {!isStreaming && unlinked.map((a) => <PendingArtifactCard key={a.id} artifact={a} />)}

              {!isStreaming && pendingConfirmation && (
                <ToolCallIndicator
                  toolName={pendingConfirmation.toolName}
                  status="waiting"
                  resultPreview="waiting for your approval below"
                />
              )}

              {isStreaming && (
                <div className="grid gap-2.5">
                  {thinkingContent && (
                    <ThinkingBlock
                      content={thinkingContent}
                      autoExpanded={streamingContent.length === 0}
                      streaming
                    />
                  )}
                  {currentToolCall && (
                    <ToolCallIndicator
                      toolName={currentToolCall.name}
                      status={currentToolCall.status}
                      resultPreview={currentToolCall.resultPreview}
                    />
                  )}
                  <StreamingIndicator content={streamingContent} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="relative flex-none pb-5 before:pointer-events-none before:absolute before:inset-x-0 before:-top-8 before:h-8 before:bg-gradient-to-t before:from-canvas before:to-transparent">
        <div className={COLUMN}>
          {limit ? (
            <LimitNotice limit={limit} onRetry={(text) => send(text, { retry: true })} />
          ) : (
            <>
              {error && (
                <div
                  role="alert"
                  className="mb-2.5 flex items-start justify-between gap-3 rounded-[10px] border border-risk-line bg-risk-soft px-3 py-2 text-[13px]"
                >
                  <span>{error}</span>
                  <button type="button" onClick={clearError} className="btn btn-ghost btn-sm">
                    Dismiss
                  </button>
                </div>
              )}
              {pendingConfirmation && !isStreaming ? (
                <ComposerApproval confirmation={pendingConfirmation} />
              ) : (
                <ChatInput
                  key={draft.key}
                  initialValue={draft.text}
                  onSend={(text) => send(text)}
                  busy={isStreaming}
                  hint={FOOTER_NOTE}
                  chips={
                    subject && (
                      <SubjectChip
                        icon={<Activity className="h-3.5 w-3.5 text-fg-2" />}
                        label={subject.name}
                        onRemove={() => setSubject(null)}
                      />
                    )
                  }
                  placeholder="Ask a follow-up"
                />
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
