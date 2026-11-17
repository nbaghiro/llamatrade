import { ArtifactType, MessageRole } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { Code2, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import {
  UNTITLED_STRATEGY,
  useStrategyBuilderStoreWithContext,
} from '../../../store/strategy-builder';
import { ChatMessage } from '../../agent/ChatMessage';
import { proposalDsl } from '../copilot/evidence';

import { questionsFirstPrompt, SKIP_PROMPT } from './draftPrompts';

interface DraftQuestionsProps {
  description: string;
  onDone: () => void;
  onCancel: () => void;
}

/** draft2 B: Copilot asks what could mean several things, and the draft fills in beside it. */
export function DraftQuestions({ description, onDone, onCancel }: DraftQuestionsProps) {
  const store = useStrategyBuilderStoreWithContext();
  const { messages, pendingArtifacts, isStreaming, streamingContent, error } = useAgentStore();
  const sendMessage = useAgentStore((s) => s.sendMessage);
  const startNewChat = useAgentStore((s) => s.startNewChat);
  const dismissArtifact = useAgentStore((s) => s.dismissArtifact);
  const [reply, setReply] = useState('');
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    startNewChat();
    sendMessage(
      questionsFirstPrompt(description),
      undefined,
      store.strategyName,
      'strategy-builder'
    ).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const draft = useMemo(() => {
    const artifact = [...pendingArtifacts]
      .reverse()
      .find((a) => a.artifactType === ArtifactType.STRATEGY && !a.isCommitted);
    if (!artifact) return null;
    const dsl = proposalDsl(artifact.previewJson);
    return dsl && fromDSLString(dsl) ? { artifact, dsl } : null;
  }, [pendingArtifacts]);

  const replies = messages.filter((m, i) => !(i === 0 && m.role === MessageRole.USER));
  const answered = messages.filter((m) => m.role === MessageRole.USER).length - 1;

  const send = (text: string) => {
    if (!text.trim() || isStreaming) return;
    sendMessage(text.trim(), undefined, store.strategyName, 'strategy-builder').catch(
      () => undefined
    );
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(reply);
    setReply('');
  };

  const useDraft = () => {
    if (!draft) return;
    const name = draft.artifact.name;
    if (!store.applyDSL(draft.dsl)) return;
    if (store.strategyName === UNTITLED_STRATEGY && name) store.setStrategyName(name);
    if (!store.strategyDescription) store.setStrategyDescription(description);
    dismissArtifact(draft.artifact.id);
    onDone();
  };

  const lines = draft ? draft.dsl.split('\n') : [];
  return (
    <div className="grid min-h-[480px] overflow-hidden rounded-panel border border-line bg-panel lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.62fr)]">
      <div className="grid content-start gap-4 p-5">
        <div className="grid justify-items-end">
          <div className="max-w-[90%] whitespace-pre-wrap rounded-[10px] bg-fg px-[14px] py-[10px] text-[14px] text-canvas">
            {description}
          </div>
        </div>
        <p className="m-0 flex items-start gap-2 text-[12.5px] text-fg-2">
          <Sparkles className="mt-0.5 h-3.5 w-3.5 flex-none text-accent" aria-hidden="true" />
          Copilot asks about anything here that could mean more than one rule before it writes the
          draft. Answer in your own words, or skip and it uses the option it would pick.
        </p>
        {replies.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        {isStreaming && (
          <div className="whitespace-pre-wrap text-[14px] text-fg-2">
            {streamingContent || 'Copilot is reading the description'}
          </div>
        )}
        {error && !isStreaming && (
          <p
            role="alert"
            className="m-0 flex flex-wrap items-center gap-x-2 text-[12.5px] text-risk"
          >
            Copilot couldn’t answer just now. Your description is kept above.
            <button
              type="button"
              onClick={() => send(questionsFirstPrompt(description))}
              className="text-accent hover:underline"
            >
              Try again
            </button>
          </p>
        )}
        <form onSubmit={submit} className="grid gap-2">
          <label className="sr-only" htmlFor="draft-reply">
            Answer Copilot
          </label>
          <textarea
            id="draft-reply"
            rows={2}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Answer here"
            className="input resize-none py-2"
          />
          <span className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={onCancel} className="btn btn-ghost btn-sm">
              Back
            </button>
            <button
              type="button"
              onClick={() => send(SKIP_PROMPT)}
              disabled={isStreaming || draft !== null}
              className="btn btn-ghost btn-sm"
            >
              Skip, use its picks
            </button>
            <button
              type="submit"
              disabled={!reply.trim() || isStreaming}
              className="btn btn-primary btn-sm ml-auto"
            >
              Answer
            </button>
          </span>
        </form>
      </div>
      <aside className="flex min-w-0 flex-col border-t border-line bg-canvas lg:border-l lg:border-t-0">
        <header className="flex items-center gap-2 border-b border-line px-4 py-3">
          <Code2 className="h-4 w-4 text-fg-3" aria-hidden="true" />
          <b className="text-[13px] font-semibold">Draft so far</b>
          <span className="ml-auto text-[11.5px] text-fg-3">
            {draft
              ? 'Ready'
              : answered > 0
                ? `${answered} ${answered === 1 ? 'answer' : 'answers'} sent`
                : 'Waiting on the questions'}
          </span>
        </header>
        {draft ? (
          <>
            <pre className="m-0 flex-1 overflow-auto px-2 py-3 font-mono text-[12.5px] leading-[1.75]">
              {lines.map((l, i) => (
                <div key={i} className="grid grid-cols-[32px_minmax(0,1fr)] gap-2">
                  <span className="select-none text-right text-fg-3">{i + 1}</span>
                  <span className="whitespace-pre-wrap text-fg">{l}</span>
                </div>
              ))}
            </pre>
            <div className="flex items-center gap-2 border-t border-line px-4 py-3">
              <span className="text-[12px] text-fg-3">Opens as an unsaved draft.</span>
              <button type="button" onClick={useDraft} className="btn btn-primary btn-sm ml-auto">
                Use this draft
              </button>
            </div>
          </>
        ) : (
          <p className="m-0 px-4 py-6 text-[12.5px] text-fg-3">
            The code appears here once Copilot writes it. Nothing is added to the editor until you
            choose to use it.
          </p>
        )}
      </aside>
    </div>
  );
}
