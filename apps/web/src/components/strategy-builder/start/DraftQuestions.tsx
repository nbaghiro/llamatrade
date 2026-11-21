import { ArtifactType, MessageRole } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { ListTree } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import { buildOutline, metaParts } from '../../../lib/outline';
import {
  UNTITLED_STRATEGY,
  useStrategyBuilderStoreWithContext,
} from '../../../store/strategy-builder';
import { ChatMessage } from '../../agent/ChatMessage';
import { DraftChoices } from '../../agent/DraftChoices';
import {
  answersMessage,
  DEFAULTS_MESSAGE,
  draftRequest,
  hideDraftBlock,
  presetPicks,
  type DraftPicks,
} from '../../agent/draftQuestions';
import { CopilotMark } from '../../common/Logo';
import { proposalDsl } from '../copilot/evidence';
import { Outline, Parts } from '../outline/Outline';

import { readDraftQuestions } from './questionParse';

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
    sendMessage(draftRequest(description), undefined, store.strategyName, 'strategy-builder').catch(
      () => undefined
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const draft = useMemo(() => {
    const artifact = [...pendingArtifacts]
      .reverse()
      .find((a) => a.artifactType === ArtifactType.STRATEGY && !a.isCommitted);
    if (!artifact) return null;
    const dsl = proposalDsl(artifact.previewJson);
    const parsed = dsl ? fromDSLString(dsl) : null;
    return dsl && parsed ? { artifact, dsl, parsed } : null;
  }, [pendingArtifacts]);

  const lastAssistant = [...messages].reverse().find((m) => m.role === MessageRole.ASSISTANT);
  const ask = useMemo(
    () => (lastAssistant ? readDraftQuestions(lastAssistant.content) : null),
    [lastAssistant]
  );
  const questions = ask?.questions ?? [];

  const [picks, setPicks] = useState<DraftPicks>({});
  const [answered, setAnswered] = useState<ReadonlySet<string>>(new Set());
  const [sentAnswers, setSentAnswers] = useState(false);
  const askKey = questions.map((q) => q.id).join('|');
  useEffect(() => {
    setPicks(presetPicks(questions));
    setAnswered(new Set());
    setSentAnswers(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askKey]);

  const send = (text: string) => {
    if (!text.trim() || isStreaming) return;
    sendMessage(text.trim(), undefined, store.strategyName, 'strategy-builder').catch(
      () => undefined
    );
  };

  const choose = (id: string, value: string) => {
    setPicks((p) => ({ ...p, [id]: value }));
    setAnswered((a) => new Set(a).add(id));
  };

  const writeDraft = (finalPicks: DraftPicks) => {
    setPicks(finalPicks);
    setAnswered(new Set(questions.map((q) => q.id)));
    setSentAnswers(true);
    send(answersMessage(questions, finalPicks));
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

  const cards = questions.length > 0 && !draft;
  const answeredCount = questions.filter((q) => answered.has(q.id)).length;

  const replies = messages.filter((m, i) => !(i === 0 && m.role === MessageRole.USER));
  const draftLines = useMemo(() => (draft ? buildOutline(draft.parsed.tree) : []), [draft]);

  return (
    <div className="grid min-h-[520px] overflow-hidden rounded-panel border border-line bg-panel lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.62fr)]">
      <div className="grid content-start gap-4 p-5">
        <div className="grid justify-items-end">
          <div className="max-w-[90%] whitespace-pre-wrap rounded-[10px] bg-fg px-[14px] py-[10px] text-[14px] text-canvas">
            {description}
          </div>
        </div>

        {cards ? (
          <>
            <p className="m-0 flex items-start gap-2 text-[12.5px] text-fg-2">
              <CopilotMark className="mt-0.5 h-3.5 w-3.5 flex-none text-fg" />
              {ask?.intro ||
                `${questions.length === 1 ? 'One part' : `${questions.length} parts`} of this could mean more than one rule. Pick what you meant, or use Copilot's defaults.`}
            </p>
            <DraftChoices
              key={askKey}
              questions={questions}
              disabled={isStreaming}
              answered={sentAnswers}
              onChange={choose}
              onDraft={writeDraft}
              onDefaults={() => {
                setSentAnswers(true);
                send(DEFAULTS_MESSAGE);
              }}
            />
            {sentAnswers && (
              <p className="m-0 text-[12.5px] text-fg-2">
                {isStreaming ? 'Copilot is writing the draft.' : 'Answers sent.'}
              </p>
            )}
          </>
        ) : (
          <>
            <p className="m-0 flex items-start gap-2 text-[12.5px] text-fg-2">
              <CopilotMark className="mt-0.5 h-3.5 w-3.5 flex-none text-fg" />
              Copilot asks about anything here that could mean more than one rule before it writes
              the draft. Answer in your own words, or skip and it uses the option it would pick.
            </p>
            {replies.map((m) => (
              <ChatMessage key={m.id} message={m} />
            ))}
          </>
        )}

        {isStreaming && (
          <div className="whitespace-pre-wrap text-[14px] text-fg-2">
            {hideDraftBlock(streamingContent) || 'Copilot is reading the description'}
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
              onClick={() => send(draftRequest(description))}
              className="text-accent hover:underline"
            >
              Try again
            </button>
          </p>
        )}
        {(!cards || !sentAnswers) && (
          <form onSubmit={submit} className="grid gap-2">
            <label className="sr-only" htmlFor="draft-reply">
              Answer Copilot
            </label>
            <textarea
              id="draft-reply"
              rows={2}
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder={cards ? 'Or answer in your own words' : 'Answer here'}
              className="input resize-none py-2"
            />
            <span className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={onCancel} className="btn btn-ghost btn-sm">
                Back
              </button>
              {!cards && (
                <button
                  type="button"
                  onClick={() => send(DEFAULTS_MESSAGE)}
                  disabled={isStreaming || draft !== null}
                  className="btn btn-ghost btn-sm"
                >
                  Skip, use its picks
                </button>
              )}
              <button
                type="submit"
                disabled={!reply.trim() || isStreaming}
                className="btn btn-primary btn-sm ml-auto"
              >
                Answer
              </button>
            </span>
          </form>
        )}
      </div>

      <aside className="flex min-w-0 flex-col border-t border-line bg-canvas lg:border-l lg:border-t-0">
        <header className="flex items-center gap-2 border-b border-line px-4 py-3">
          <ListTree className="h-4 w-4 text-fg-3" aria-hidden="true" />
          <b className="text-[13px] font-semibold">Draft so far</b>
          <span className="ml-auto text-[11.5px] text-fg-3">
            {draft
              ? 'Ready'
              : questions.length > 0
                ? `${answeredCount} of ${questions.length} answered`
                : 'Waiting on the questions'}
          </span>
        </header>
        {draft ? (
          <>
            <div className="flex-1 overflow-auto px-3 py-3">
              <p className="m-0 px-1 pb-2 text-[13px] text-fg-2">
                <Parts
                  parts={metaParts({
                    timeframe: draft.parsed.metadata.timeframe ?? '1D',
                    benchmark: draft.parsed.metadata.benchmark ?? '',
                  })}
                />
              </p>
              <Outline lines={draftLines} dense label="The drafted rules" />
            </div>
            <div className="flex items-center gap-2 border-t border-line px-4 py-3">
              <span className="text-[12px] text-fg-3">Opens as an unsaved draft.</span>
              <button type="button" onClick={useDraft} className="btn btn-primary btn-sm ml-auto">
                Use this draft
              </button>
            </div>
          </>
        ) : questions.length > 0 ? (
          <>
            <ol className="m-0 grid flex-1 list-none content-start gap-0 p-0">
              {questions.map((q, i) => {
                const done = answered.has(q.id);
                return (
                  <li
                    key={q.id}
                    className={`grid grid-cols-[22px_minmax(0,1fr)] gap-2 border-b border-line px-4 py-2.5 text-[13px] ${
                      done ? 'shadow-[inset_2px_0_0_rgb(var(--accent))]' : ''
                    }`}
                  >
                    <span className="font-mono text-[11.5px] text-fg-3">{i + 1}</span>
                    <span>
                      <span className="block text-[12px] text-fg-3">{q.short || q.label}</span>
                      <span className={done ? 'text-fg' : 'text-fg-3'}>
                        {done ? picks[q.id] : `${q.preset}, unless you choose otherwise`}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ol>
            <p className="m-0 px-4 py-3 text-[12px] leading-[1.55] text-fg-3">
              Copilot writes the rules once the questions are answered. Nothing is added to the
              editor until you choose to use them.
            </p>
            <footer className="flex gap-4 border-t border-line px-4 py-2.5 text-[11.5px] text-fg-3">
              <span className="flex items-center gap-1.5">
                <i className="inline-block h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                From your answers
              </span>
              <span className="flex items-center gap-1.5">
                <i
                  className="inline-block h-1.5 w-1.5 rounded-full bg-line-strong"
                  aria-hidden="true"
                />
                Waiting on a question
              </span>
            </footer>
          </>
        ) : (
          <p className="m-0 px-4 py-6 text-[12.5px] text-fg-3">
            The rules appear here once Copilot writes them. Nothing is added to the editor until you
            choose to use them.
          </p>
        )}
      </aside>
    </div>
  );
}
