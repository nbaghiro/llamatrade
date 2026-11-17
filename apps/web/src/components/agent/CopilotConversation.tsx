/**
 * The Copilot thread and composer, shared by the full page, the side panel and the New Strategy
 * dialog. Each surface supplies only its own frame around this.
 */

import { useAgentStore, type ResolvedConfirmation } from '@llamatrade/core/stores/agent';
import { Activity, AlertTriangle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { ChatInput, SubjectChip } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { ComposerApproval } from './ComposerApproval';
import { PendingArtifactCard } from './PendingArtifactCard';
import { threadSources } from './sources';
import { SourcesPane } from './SourcesPane';
import { StreamingIndicator } from './StreamingIndicator';
import { askPlaceholder } from './subjects';
import { useCopilotSubject } from './subjectStore';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallIndicator } from './ToolCallIndicator';
import { ToolConfirmationCard } from './ToolConfirmationCard';
import { useCopilotSend } from './useCopilotSend';

type Variant = 'page' | 'panel' | 'modal';

const COLUMN: Record<Variant, string> = {
  page: 'mx-auto w-full max-w-[680px] px-4 md:px-6',
  panel: 'w-full px-4',
  modal: 'mx-auto w-full max-w-[760px] px-6',
};

const DEFAULT_NOTE = 'Copilot proposes, you confirm';

interface CopilotConversationProps {
  variant: Variant;
  /** UI context passed to sendMessage and getSuggestedPrompts. */
  page: string;
  /** Shown while the thread is empty. */
  emptyState: ReactNode;
  placeholder?: string;
  footerNote?: ReactNode;
  /** Starter prompts when the service suggests none. */
  fallbackPrompts?: string[];
  /** Takes the store's one-shot seed prompt into the composer. */
  consumeSeed?: boolean;
  /** Shows what each tool call returned in a pane beside the thread, on wide screens. */
  showSources?: boolean;
  /** Folds long replies to three lines, for the phone's half sheet. */
  folded?: boolean;
  /** Replaces the thread when Copilot can't be reached and a question was kept. */
  unavailableView?: ReactNode;
}

/** The outage notice that sits above the disabled composer. */
export function CopilotUnavailableNotice({
  onRetry,
  historyShown,
}: {
  onRetry: () => void;
  /** Whether any saved conversation is on screen, which decides what the notice can promise. */
  historyShown: boolean;
}) {
  const unsent = useCopilotSubject((s) => s.unsent);
  return (
    <div
      role="status"
      className="mb-2.5 flex items-start gap-3 rounded-[8px] border border-risk-line bg-risk-soft px-3.5 py-2.5 text-[13px] text-fg"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-none text-risk" />
      <span className="min-w-0 flex-1">
        <b className="font-semibold">Copilot is unavailable.</b>{' '}
        <span className="text-fg-2">
          {unsent
            ? 'Your question was kept and nothing was sent. Sessions, orders and backtests aren’t affected.'
            : historyShown
              ? 'Your conversations are saved and you can read them. Sessions, orders and backtests aren’t affected.'
              : 'Your conversations are saved and will show here when it’s back. Sessions, orders and backtests aren’t affected.'}
        </span>
      </span>
      <button type="button" className="btn btn-secondary btn-sm flex-none" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

export function CopilotConversation({
  variant,
  page,
  emptyState,
  placeholder,
  footerNote = DEFAULT_NOTE,
  fallbackPrompts = [],
  consumeSeed = true,
  showSources = false,
  folded = false,
  unavailableView,
}: CopilotConversationProps) {
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
    suggestedPrompts,
    seedPrompt,
    serviceUnavailable,
    loading,
    error,
    getSuggestedPrompts,
    clearError,
    clearSeedPrompt,
    loadSessions,
    sessions,
  } = useAgentStore();
  const subject = useCopilotSubject((s) => s.subject);
  const setSubject = useCopilotSubject((s) => s.setSubject);
  const unsent = useCopilotSubject((s) => s.unsent);
  const send = useCopilotSend(page);
  const sessionsCount = sessions.length;

  const endRef = useRef<HTMLDivElement>(null);
  const wasStreaming = useRef(false);
  const [draft, setDraft] = useState({ text: '', key: 0 });
  const [activeSource, setActiveSource] = useState<number | null>(null);

  useEffect(() => {
    if (!consumeSeed || !seedPrompt) return;
    setDraft((d) => ({ text: seedPrompt, key: d.key + 1 }));
    clearSeedPrompt();
  }, [consumeSeed, seedPrompt, clearSeedPrompt]);

  useEffect(() => {
    getSuggestedPrompts({ page });
  }, [page, getSuggestedPrompts]);

  useEffect(() => {
    if (wasStreaming.current && !isStreaming) loadSessions();
    wasStreaming.current = isStreaming;
  }, [isStreaming, loadSessions]);

  useEffect(() => {
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    endRef.current?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'end' });
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

  const column = COLUMN[variant];
  const chips = (suggestedPrompts.length ? suggestedPrompts : fallbackPrompts).slice(0, 3);
  const empty = messages.length === 0 && !isStreaming && resolvedConfirmations.length === 0;
  const withSources = showSources && !empty;
  const kept = serviceUnavailable && unsent && unavailableView;

  const thread = (
    <div className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
      <div className={`${column} ${variant === 'page' ? 'py-7' : 'py-5'}`}>
        {kept ? (
          unavailableView
        ) : loading && messages.length === 0 ? (
          <div className="grid gap-3" aria-busy="true">
            <span className="sr-only" role="status">
              Loading the conversation
            </span>
            <div className="ml-auto h-9 w-2/3 rounded-[12px] bg-sunk motion-safe:animate-pulse" />
            <div className="h-16 w-full rounded-[8px] bg-sunk motion-safe:animate-pulse" />
          </div>
        ) : empty ? (
          serviceUnavailable ? null : (
            emptyState
          )
        ) : (
          <div className="grid gap-[22px]">
            {answered(null)}
            {messages.map((m) => (
              <div key={m.id} className="grid gap-[18px]">
                <ChatMessage
                  message={m}
                  artifacts={artifactMap}
                  firstSource={firstSource.get(m.id)}
                  activeSource={activeSource}
                  onCite={showSources ? setActiveSource : undefined}
                  folded={folded}
                />
                {answered(m.id)}
              </div>
            ))}

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
        <div ref={endRef} />
      </div>
    </div>
  );

  const composer = (
    <div className={`flex-none ${variant === 'page' ? 'pb-5' : 'border-t border-line pb-3 pt-3'}`}>
      <div className={column}>
        {serviceUnavailable && !kept && (
          <CopilotUnavailableNotice
            onRetry={() => loadSessions()}
            historyShown={!empty || sessionsCount > 0}
          />
        )}
        {error && !serviceUnavailable && (
          <div
            role="alert"
            className="mb-2.5 flex items-start justify-between gap-3 rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2 text-[13px]"
          >
            <span>{error}</span>
            <button type="button" onClick={clearError} className="btn btn-ghost btn-sm">
              Dismiss
            </button>
          </div>
        )}
        {empty && chips.length > 0 && !serviceUnavailable && (
          <div className="no-scrollbar mb-2.5 flex gap-2 overflow-x-auto md:flex-wrap md:overflow-visible">
            {chips.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => send(prompt)}
                disabled={isStreaming}
                className="inline-flex h-7 flex-none items-center rounded-full border border-line-strong px-3 text-[12.5px] text-fg-2 hover:border-accent hover:text-fg disabled:opacity-45"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
        {pendingConfirmation && !isStreaming ? (
          <ComposerApproval confirmation={pendingConfirmation} />
        ) : (
          <ChatInput
            key={draft.key}
            initialValue={draft.text}
            onSend={send}
            disabled={serviceUnavailable}
            busy={isStreaming}
            hint={footerNote}
            chips={
              subject && (
                <SubjectChip
                  icon={<Activity className="h-3.5 w-3.5 text-accent" />}
                  label={subject.name}
                  onRemove={() => setSubject(null)}
                />
              )
            }
            placeholder={
              serviceUnavailable
                ? 'Copilot is unavailable'
                : (placeholder ??
                  (empty
                    ? subject
                      ? askPlaceholder(subject)
                      : 'Ask Copilot to build, edit or explain a strategy'
                    : 'Ask a follow-up'))
            }
          />
        )}
      </div>
    </div>
  );

  if (!withSources) {
    return (
      <>
        {thread}
        {composer}
      </>
    );
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        {thread}
        {composer}
      </div>
      <SourcesPane
        sources={sources}
        active={activeSource}
        className="hidden w-[384px] flex-none border-l border-line bg-canvas lg:flex"
      />
    </div>
  );
}
