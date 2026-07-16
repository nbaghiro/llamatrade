/**
 * Shared Copilot conversation core — the message thread + composer, driven by
 * the global agent store. This is the single source of chat UI/logic reused by
 * every Copilot surface (full page, side panel, New Strategy modal) so they stay
 * behaviourally identical; each surface supplies only its own shell (sidebar,
 * resize, header) around this.
 */

import { useEffect, useMemo, useRef, type ReactNode } from 'react';

import { useAgentStore } from '../../store/agent';

import { ChatInput } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { PendingArtifactCard } from './PendingArtifactCard';
import { StreamingIndicator } from './StreamingIndicator';
import { ToolCallIndicator } from './ToolCallIndicator';
import { ToolConfirmationCard } from './ToolConfirmationCard';

type Variant = 'page' | 'panel' | 'modal';

interface Sizing {
  threadInner: string;
  msgSpace: string;
  composerPad: string;
  composerInner: string;
  chip: string;
  footer: string;
}

const SIZING: Record<Variant, Sizing> = {
  page: {
    threadInner: 'mx-auto max-w-[820px] px-6 py-7',
    msgSpace: 'space-y-5',
    composerPad: 'px-6 py-4',
    composerInner: 'mx-auto max-w-[820px]',
    chip: 'px-2.5 py-1.5 text-[10.5px]',
    footer: 'text-[10px]',
  },
  panel: {
    threadInner: 'px-4 py-4',
    msgSpace: 'space-y-4',
    composerPad: 'px-4 py-3',
    composerInner: '',
    chip: 'px-2 py-1 text-[9.5px]',
    footer: 'text-[9px]',
  },
  modal: {
    threadInner: 'mx-auto max-w-[760px] px-6 py-6',
    msgSpace: 'space-y-4',
    composerPad: 'px-6 py-4',
    composerInner: 'mx-auto max-w-[760px]',
    chip: 'px-2.5 py-1.5 text-[10.5px]',
    footer: 'text-[10px]',
  },
};

interface CopilotConversationProps {
  variant: Variant;
  /** UI context string threaded to sendMessage + getSuggestedPrompts. */
  page: string;
  /** Rendered when the conversation is empty and not streaming. */
  emptyState: ReactNode;
  placeholder?: string;
  /** Trailing hint shown next to the ⏎/⇧⏎ keys in the composer footer. */
  footerNote?: ReactNode;
  /** Suggested-prompt chips to show when the service returns none. */
  fallbackPrompts?: string[];
  /** Prefill the composer from the store's one-shot seedPrompt (full page). */
  consumeSeed?: boolean;
  /** Grid backdrop behind the thread (full page). */
  gridBackdrop?: boolean;
}

export function CopilotConversation({
  variant,
  page,
  emptyState,
  placeholder,
  footerNote,
  fallbackPrompts = [],
  consumeSeed = false,
  gridBackdrop = false,
}: CopilotConversationProps) {
  const {
    messages,
    pendingArtifacts,
    pendingArtifactIdsForCurrentMessage,
    isStreaming,
    streamingContent,
    currentToolCall,
    pendingConfirmation,
    suggestedPrompts,
    seedPrompt,
    serviceUnavailable,
    error,
    sendMessage,
    getSuggestedPrompts,
    clearError,
    clearSeedPrompt,
    loadSessions,
  } = useAgentStore();

  const threadEndRef = useRef<HTMLDivElement>(null);
  const prevStreaming = useRef(false);

  // One-shot: capture the seed on mount, then clear it from the store.
  const initialValue = useRef(consumeSeed ? seedPrompt : '').current;
  useEffect(() => {
    if (consumeSeed && seedPrompt) clearSeedPrompt();
  }, [consumeSeed, seedPrompt, clearSeedPrompt]);

  useEffect(() => {
    getSuggestedPrompts({ page });
  }, [page, getSuggestedPrompts]);

  // Refresh the session list once a streamed reply finishes (title resolves /
  // a new session may exist).
  useEffect(() => {
    if (prevStreaming.current && !isStreaming) loadSessions();
    prevStreaming.current = isStreaming;
  }, [isStreaming, loadSessions]);

  // Auto-scroll to the latest turn as tokens / tools / artifacts arrive.
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, currentToolCall, pendingArtifacts.length, pendingConfirmation]);

  const artifactMap = useMemo(() => {
    const map = new Map<string, (typeof pendingArtifacts)[number]>();
    for (const a of pendingArtifacts) map.set(a.id, a);
    return map;
  }, [pendingArtifacts]);

  // Artifacts that belong to no message and aren't mid-stream (e.g. reloaded).
  const unlinkedArtifacts = useMemo(() => {
    const linked = new Set<string>();
    for (const m of messages) for (const id of m.inlineArtifactIds ?? []) linked.add(id);
    const inFlight = new Set(pendingArtifactIdsForCurrentMessage);
    return pendingArtifacts.filter((a) => !linked.has(a.id) && !inFlight.has(a.id));
  }, [messages, pendingArtifacts, pendingArtifactIdsForCurrentMessage]);

  const size = SIZING[variant];
  const chips = (suggestedPrompts.length > 0 ? suggestedPrompts : fallbackPrompts).slice(0, 3);
  const disabled = isStreaming || serviceUnavailable;
  const handleSend = (content: string) => sendMessage(content, undefined, undefined, page);

  return (
    <>
      {/* Thread */}
      <div
        className={`min-h-0 flex-1 overflow-x-hidden overflow-y-auto ${gridBackdrop ? 'bg-grid' : ''}`}
      >
        <div className={size.threadInner}>
          {messages.length === 0 && !isStreaming ? (
            emptyState
          ) : (
            <div className={size.msgSpace}>
              {messages.map((m) => (
                <ChatMessage key={m.id} message={m} artifacts={artifactMap} />
              ))}

              {!isStreaming &&
                unlinkedArtifacts.map((a) => (
                  <div key={a.id} className="pl-[50px]">
                    <PendingArtifactCard artifact={a} />
                  </div>
                ))}

              {!isStreaming && <ToolConfirmationCard />}

              {isStreaming && (
                <div className="space-y-2.5">
                  <StreamingIndicator content={streamingContent} />
                  {currentToolCall && (
                    <div className="pl-[50px]">
                      <ToolCallIndicator
                        toolName={currentToolCall.name}
                        status={currentToolCall.status}
                        resultPreview={currentToolCall.resultPreview}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <div ref={threadEndRef} />
        </div>
      </div>

      {/* Composer */}
      <div className={`flex-none border-t-2 border-ink bg-paper/70 ${size.composerPad}`}>
        <div className={size.composerInner}>
          {error && !serviceUnavailable && (
            <div className="mb-2.5 flex items-start justify-between gap-3 border-2 border-ink bg-red-50 px-3 py-2 text-[13px] text-red-700">
              <span>{error}</span>
              <button onClick={clearError} className="font-mono text-xs underline">
                Dismiss
              </button>
            </div>
          )}

          {chips.length > 0 && (
            <div className="mb-2.5 flex flex-nowrap gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {chips.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  disabled={disabled}
                  className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap border-2 border-ink bg-paper font-mono font-bold uppercase tracking-[0.03em] text-ink shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-y-0.5 disabled:opacity-40 disabled:shadow-none ${size.chip}`}
                >
                  <span className="text-orange-500">＋</span>
                  {prompt}
                </button>
              ))}
            </div>
          )}

          <ChatInput
            onSend={handleSend}
            disabled={disabled}
            initialValue={initialValue}
            placeholder={
              serviceUnavailable
                ? 'Copilot service unavailable…'
                : (placeholder ?? 'Ask Copilot to build, edit, or explain a strategy')
            }
          />

          <div
            className={`mt-2 flex flex-wrap items-center gap-3 font-mono uppercase tracking-[0.05em] text-ink/40 ${size.footer}`}
          >
            <span>
              <span className="border border-line px-1 py-px">⏎</span> Send{' '}
              <span className="border border-line px-1 py-px">⇧⏎</span> Newline
            </span>
            {footerNote && <span>{footerNote}</span>}
          </div>
        </div>
      </div>
    </>
  );
}
