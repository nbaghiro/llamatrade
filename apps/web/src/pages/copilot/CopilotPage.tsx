import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { History, Plus } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { CopilotConversation } from '../../components/agent/CopilotConversation';
import { CHAT_HOME, conversationPath, HISTORY_PATH } from '../../components/agent/entry';
import { buildSubjects, canvasStarters, findSubject } from '../../components/agent/subjects';
import { useCopilotSubject } from '../../components/agent/subjectStore';
import { useCopilotSend } from '../../components/agent/useCopilotSend';
import { etToday } from '../../components/sessions/sessionRows';
import { useSessionRows } from '../../components/shell/useSessionRows';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

import { HistoryView } from './HistoryView';
import { OpenCanvas } from './OpenCanvas';
import { SubjectBrief } from './SubjectBrief';
import { useFillHeight } from './useFillHeight';

const PAGE = 'copilot';
const SUBJECT_WAIT_MS = 2000;
const HEIGHT = 'h-[calc(100dvh-56px-84px)] md:h-[calc(100dvh-56px)]';

/**
 * Home (/dashboard): a large composer with suggestions; ?about= opens the brief for one subject.
 * /copilot/:sessionId: the conversation in a centred column with the composer pinned under it.
 * ?view=history: earlier conversations, searched by what was said (history2 A).
 */
export default function CopilotPage() {
  const { sessionId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const {
    sessions,
    sessionsLoading,
    currentSessionId,
    messages,
    isStreaming,
    serviceUnavailable,
    seedPrompt,
    loadSessions,
    selectSession,
    deleteSession,
    startNewChat,
    clearSeedPrompt,
  } = useAgentStore();
  const subject = useCopilotSubject((s) => s.subject);
  const setSubject = useCopilotSubject((s) => s.setSubject);
  const unsent = useCopilotSubject((s) => s.unsent);
  const send = useCopilotSend(PAGE);
  const routed = useRef<string | undefined>(undefined);
  const [fillRef, fillHeight] = useFillHeight<HTMLDivElement>();
  const fill = fillHeight === null ? undefined : { height: fillHeight };
  const [draft, setDraft] = useState({ text: '', key: 0 });

  const rows = useSessionRows();
  const strategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const runs = useBacktestStore((s) => s.backtests);
  const listBacktests = useBacktestStore((s) => s.listBacktests);

  const view = params.get('view');
  const about = params.get('about');
  const groups = useMemo(
    () => buildSubjects(rows, strategies, runs, etToday()),
    [rows, strategies, runs]
  );

  useEffect(() => {
    loadSessions();
    if (useStrategiesStore.getState().strategies.length === 0) fetchStrategies();
    if (useBacktestStore.getState().backtests.length === 0) listBacktests();
  }, [loadSessions, fetchStrategies, listBacktests]);

  useEffect(() => {
    if (!about) return;
    const found = findSubject(groups, about);
    if (found && found.key !== subject?.key) setSubject(found);
  }, [about, groups, subject?.key, setSubject]);

  const [asking, setAsking] = useState<{ q: string; about: string | null } | null>(null);

  useEffect(() => {
    const q = params.get('q');
    if (!q) return;
    startNewChat();
    if (params.get('send') === '1') setAsking({ q, about });
    else setDraft((d) => ({ text: q, key: d.key + 1 }));
    const next = new URLSearchParams(params);
    next.delete('q');
    next.delete('send');
    setParams(next, { replace: true });
    if (sessionId) navigate(`${CHAT_HOME}?${next.toString()}`, { replace: true });
  }, [params, setParams, startNewChat, sessionId, navigate, about]);

  // A question from a marker is sent once its subject is chosen, or after a short wait when the
  // subject can't be found, so it still goes out with the account as context.
  useEffect(() => {
    if (!asking || isStreaming) return;
    const ready = !asking.about || subject?.key === asking.about;
    const go = () => {
      setAsking(null);
      send(asking.q).catch(() => undefined);
    };
    if (ready) {
      go();
      return;
    }
    const timer = setTimeout(go, SUBJECT_WAIT_MS);
    return () => clearTimeout(timer);
  }, [asking, isStreaming, subject?.key, send]);

  useEffect(() => {
    if (!seedPrompt || sessionId || messages.length) return;
    setDraft((d) => ({ text: seedPrompt, key: d.key + 1 }));
    clearSeedPrompt();
  }, [seedPrompt, sessionId, messages.length, clearSeedPrompt]);

  useEffect(() => {
    if (routed.current === sessionId) return;
    routed.current = sessionId;
    if (sessionId) selectSession(sessionId);
  }, [sessionId, selectSession]);

  const wasUnavailable = useRef(serviceUnavailable);
  useEffect(() => {
    const recovered = wasUnavailable.current && !serviceUnavailable;
    wasUnavailable.current = serviceUnavailable;
    if (recovered && sessionId && currentSessionId !== sessionId) selectSession(sessionId);
  }, [serviceUnavailable, sessionId, currentSessionId, selectSession]);

  const lastStoreId = useRef(currentSessionId);
  useEffect(() => {
    if (currentSessionId === lastStoreId.current) return;
    lastStoreId.current = currentSessionId;
    if (currentSessionId && currentSessionId !== sessionId) {
      routed.current = currentSessionId;
      navigate(conversationPath(currentSessionId), { replace: !sessionId });
    }
  }, [currentSessionId, sessionId, navigate]);

  const title = sessions.find((s) => s.id === currentSessionId)?.title || 'New conversation';
  useDocumentTitle(view === 'history' ? 'Conversations' : sessionId ? title : 'Home');

  const startNew = () => {
    startNewChat();
    setSubject(null);
    routed.current = undefined;
    navigate(CHAT_HOME);
  };
  const remove = (id: string) => {
    deleteSession(id);
    if (id === sessionId) {
      routed.current = undefined;
      navigate(HISTORY_PATH, { replace: true });
    }
  };
  const choose = (key: string | null) => {
    const found = findSubject(groups, key);
    setSubject(found);
    const next = new URLSearchParams();
    if (found) next.set('about', found.key);
    setParams(next);
  };

  const landing = !sessionId && messages.length === 0 && !isStreaming && unsent === null;
  const last = landing
    ? ([...sessions].sort((a, b) =>
        Number((b.lastActivityAt?.seconds ?? 0n) - (a.lastActivityAt?.seconds ?? 0n))
      )[0] ?? null)
    : null;

  let content: ReactNode;
  if (view === 'history') {
    content = (
      <HistoryView
        sessions={sessions}
        loading={sessionsLoading}
        initialQuery={params.get('find') ?? ''}
        onQuery={(q) =>
          setParams(q ? { view: 'history', find: q } : { view: 'history' }, { replace: true })
        }
        onOpen={(id) => navigate(conversationPath(id))}
        onNew={startNew}
        onDelete={remove}
        onBack={() => navigate(CHAT_HOME)}
      />
    );
  } else if (landing && subject) {
    content = (
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SubjectBrief
          key={`${subject.key}-${draft.key}`}
          subject={subject}
          sessions={sessions}
          onSend={send}
          onClear={() => choose(null)}
          disabled={serviceUnavailable}
          busy={isStreaming}
          initialValue={draft.text}
        />
      </div>
    );
  } else if (landing) {
    content = (
      <OpenCanvas
        key={draft.key}
        starters={canvasStarters(groups)}
        last={last}
        onSend={send}
        onDraft={(text) => send(text, { draft: true })}
        disabled={serviceUnavailable}
        busy={isStreaming}
        initialValue={draft.text}
      />
    );
  } else {
    content = <CopilotConversation page={PAGE} />;
  }

  return (
    <div ref={fillRef} style={fill} className={`relative flex flex-col ${fill ? '' : HEIGHT}`}>
      {view !== 'history' && (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-center gap-2 bg-gradient-to-b from-canvas from-60% to-transparent px-4 pb-5 pt-3 md:px-6">
          {!landing && (
            <span className="min-w-0 flex-1 truncate text-[13px] text-fg-3 max-md:hidden">
              {title}
            </span>
          )}
          <span className="flex-1" />
          <div className="pointer-events-auto flex items-center gap-1">
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] text-fg-2 transition-colors hover:bg-sunk hover:text-fg"
              onClick={() => navigate(HISTORY_PATH)}
            >
              <History className="h-3.5 w-3.5" aria-hidden="true" />
              History
            </button>
            {!landing && (
              <button
                type="button"
                className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] text-fg-2 transition-colors hover:bg-sunk hover:text-fg"
                onClick={startNew}
              >
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                New chat
              </button>
            )}
          </div>
        </div>
      )}
      {content}
    </div>
  );
}
