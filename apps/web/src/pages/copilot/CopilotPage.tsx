import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { AlertTriangle, History, Plus } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { CopilotConversation } from '../../components/agent/CopilotConversation';
import { CopilotUnavailable } from '../../components/agent/CopilotUnavailable';
import { buildSubjects, canvasStarters, findSubject } from '../../components/agent/subjects';
import { useCopilotSubject } from '../../components/agent/subjectStore';
import { useCopilotSend } from '../../components/agent/useCopilotSend';
import { etToday } from '../../components/sessions/sessionRows';
import { useSessionRows } from '../../components/shell/useSessionRows';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

import { HistoryView } from './HistoryView';
import { OpenCanvas } from './OpenCanvas';
import { SubjectBrief } from './SubjectBrief';
import { SubjectChips, SubjectRail } from './SubjectRail';

const PAGE = 'copilot';
const HEIGHT = 'h-[calc(100dvh-56px-84px)] md:h-[calc(100dvh-56px)]';

/** A banner across the page while Copilot can't be reached and a question was kept. */
function OutageBanner() {
  return (
    <div
      role="status"
      className="flex flex-none items-start gap-2.5 border-b border-risk-line bg-risk-soft px-4 py-2.5 text-[13px] md:px-8"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-none text-risk" />
      <span>
        <b className="font-semibold">Copilot is unavailable.</b>{' '}
        <span className="text-fg-2">
          It can&apos;t be reached right now. Sessions, orders and backtests aren&apos;t affected.
        </span>
      </span>
    </div>
  );
}

/**
 * /copilot: choose what to ask about (page2 A) or ask from the open canvas (empty A).
 * /copilot/:sessionId: the thread with what each tool call read beside it (conversation B).
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
  const [draft, setDraft] = useState({ text: '', key: 0 });

  const rows = useSessionRows();
  const strategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const runs = useBacktestStore((s) => s.backtests);
  const listBacktests = useBacktestStore((s) => s.listBacktests);
  const tradingLoading = useTradingStore((s) => s.loading);

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

  useEffect(() => {
    const q = params.get('q');
    if (!q) return;
    startNewChat();
    setDraft((d) => ({ text: q, key: d.key + 1 }));
    const next = new URLSearchParams(params);
    next.delete('q');
    setParams(next, { replace: true });
    if (sessionId) navigate(`/copilot?${next.toString()}`, { replace: true });
  }, [params, setParams, startNewChat, sessionId, navigate]);

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
      navigate(`/copilot/${currentSessionId}`, { replace: !sessionId });
    }
  }, [currentSessionId, sessionId, navigate]);

  const title = sessions.find((s) => s.id === currentSessionId)?.title || 'New conversation';
  useDocumentTitle(view === 'history' ? 'Conversations' : sessionId ? title : 'Copilot');

  const startNew = () => {
    startNewChat();
    setSubject(null);
    routed.current = undefined;
    navigate('/copilot');
  };
  const remove = (id: string) => {
    deleteSession(id);
    if (id === sessionId) {
      routed.current = undefined;
      navigate('/copilot?view=history', { replace: true });
    }
  };
  const choose = (key: string | null) => {
    const found = findSubject(groups, key);
    setSubject(found);
    const next = new URLSearchParams();
    if (found) next.set('about', found.key);
    setParams(next);
  };

  if (view === 'history') {
    return (
      <div className={`flex ${HEIGHT}`}>
        <HistoryView
          sessions={sessions}
          loading={sessionsLoading}
          initialQuery={params.get('find') ?? ''}
          onQuery={(q) =>
            setParams(q ? { view: 'history', find: q } : { view: 'history' }, { replace: true })
          }
          onOpen={(id) => navigate(`/copilot/${id}`)}
          onNew={startNew}
          onDelete={remove}
          onBack={() => navigate('/copilot')}
        />
      </div>
    );
  }

  const landing = !sessionId && messages.length === 0 && !isStreaming;
  const kept = serviceUnavailable && unsent !== null;

  if (landing) {
    const last =
      [...sessions].sort((a, b) =>
        Number((b.lastActivityAt?.seconds ?? 0n) - (a.lastActivityAt?.seconds ?? 0n))
      )[0] ?? null;
    return (
      <div className={`flex ${HEIGHT}`}>
        <SubjectRail
          groups={groups}
          selected={subject?.key ?? null}
          onSelect={(s) => choose(s.key === subject?.key ? null : s.key)}
          onHistory={() => navigate('/copilot?view=history')}
          loading={tradingLoading}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          {kept && <OutageBanner />}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-3 md:hidden">
              <h1 className="m-0 text-[24px] font-semibold tracking-[-0.02em]">Copilot</h1>
              <div className="flex items-center text-fg-2">
                <button
                  type="button"
                  className="btn btn-ghost px-2"
                  aria-label="Conversations"
                  onClick={() => navigate('/copilot?view=history')}
                >
                  <History className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  className="btn btn-ghost px-2"
                  aria-label="New conversation"
                  onClick={startNew}
                >
                  <Plus className="h-5 w-5" />
                </button>
              </div>
            </div>
            <SubjectChips
              groups={groups}
              selected={subject?.key ?? null}
              onSelect={(s) => choose(s?.key ?? null)}
            />
            {kept ? (
              <div className="mx-auto max-w-[1040px] px-4 py-7 md:px-8">
                <CopilotUnavailable onRetry={send} />
              </div>
            ) : subject ? (
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
            ) : (
              <OpenCanvas
                key={draft.key}
                starters={canvasStarters(groups)}
                last={last}
                onSend={send}
                disabled={serviceUnavailable}
                busy={isStreaming}
                initialValue={draft.text}
              />
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col ${HEIGHT}`}>
      <div className="flex flex-none items-center gap-2 border-b border-line px-3 py-2.5 md:px-5">
        <button
          type="button"
          className="btn btn-ghost px-2"
          aria-label="Conversations"
          title="Conversations"
          onClick={() => navigate('/copilot?view=history')}
        >
          <History className="h-4 w-4" />
        </button>
        <h1 className="m-0 min-w-0 flex-1 truncate text-[15px] font-semibold">{title}</h1>
        <button type="button" className="btn btn-ghost btn-sm" onClick={startNew}>
          <Plus className="h-4 w-4" />
          New
        </button>
      </div>
      {kept && <OutageBanner />}
      <CopilotConversation
        variant="page"
        page={PAGE}
        showSources
        emptyState={null}
        unavailableView={<CopilotUnavailable onRetry={send} compact />}
      />
    </div>
  );
}
