import { useAgentStore } from '@llamatrade/core/stores/agent';
import { History, Plus, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { CopilotConversation } from '../../components/agent/CopilotConversation';
import { CopilotHistoryRail } from '../../components/agent/CopilotHistoryRail';

const PAGE = 'copilot';
const STARTERS = [
  'Build a momentum rotation with a bond hedge',
  'Explain why my portfolio moved today',
  'Backtest my last draft over five years',
];

/** /copilot and /copilot/:sessionId: conversations in a rail beside one reading column. */
export default function CopilotPage() {
  const { sessionId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const {
    sessions,
    sessionsLoading,
    currentSessionId,
    serviceUnavailable,
    loadSessions,
    selectSession,
    deleteSession,
    startNewChat,
    openSeededChat,
  } = useAgentStore();
  const [historyOpen, setHistoryOpen] = useState(false);
  const routed = useRef<string | undefined>(undefined);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    const q = params.get('q');
    if (!q) return;
    openSeededChat(q);
    setParams({}, { replace: true });
    if (sessionId) navigate('/copilot', { replace: true });
  }, [params, setParams, openSeededChat, sessionId, navigate]);

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

  const select = (id: string) => {
    setHistoryOpen(false);
    navigate(`/copilot/${id}`);
  };
  const startNew = () => {
    setHistoryOpen(false);
    startNewChat();
    routed.current = undefined;
    navigate('/copilot');
  };
  const remove = (id: string) => {
    deleteSession(id);
    if (id === sessionId) {
      routed.current = undefined;
      navigate('/copilot', { replace: true });
    }
  };

  const title = sessions.find((s) => s.id === currentSessionId)?.title || 'New conversation';

  return (
    <div className="flex h-[calc(100dvh-56px-84px)] md:h-[calc(100dvh-56px)]">
      <CopilotHistoryRail
        className={`w-full flex-none border-r border-line md:flex md:w-[270px] ${
          historyOpen ? 'flex' : 'hidden'
        }`}
        sessions={sessions}
        currentId={currentSessionId}
        loading={sessionsLoading}
        unavailable={serviceUnavailable}
        onSelect={select}
        onNew={startNew}
        onDelete={remove}
        onClose={() => setHistoryOpen(false)}
      />

      <div className={`min-w-0 flex-1 flex-col ${historyOpen ? 'hidden md:flex' : 'flex'}`}>
        <div className="flex flex-none items-center justify-between gap-3 px-4 pt-2 md:hidden">
          <h1 className="m-0 truncate text-[22px] font-semibold tracking-[-0.02em]">Copilot</h1>
          <div className="flex items-center gap-1 text-fg-2">
            <button
              type="button"
              className="btn btn-ghost px-2"
              aria-label="Conversations"
              onClick={() => setHistoryOpen(true)}
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
        <h2 className="sr-only">{title}</h2>
        <CopilotConversation
          variant="page"
          page={PAGE}
          fallbackPrompts={STARTERS}
          emptyState={
            <div className="grid justify-items-center gap-2 py-16 text-center md:py-24">
              <span className="grid h-10 w-10 place-items-center rounded-[10px] bg-sunk text-accent">
                <Sparkles className="h-5 w-5" />
              </span>
              <h2 className="m-0 text-[17px] font-semibold">Ask Copilot</h2>
              <p className="m-0 max-w-[440px] text-[13px] text-fg-2">
                Copilot builds, edits and explains strategies in the strategy language, and runs
                backtests when you approve them. Drafts stay drafts until you save them.
              </p>
            </div>
          }
        />
      </div>
    </div>
  );
}
