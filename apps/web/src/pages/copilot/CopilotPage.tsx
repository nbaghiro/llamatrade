/**
 * Full-page LlamaTrade Copilot (/copilot).
 *
 * Left: conversation-history sidebar wired to the tenant's real agent sessions
 * (ListSessions). Selecting a row loads that session's messages (GetSession).
 * Right: the shared <CopilotConversation> — thread + composer — reused across
 * every Copilot surface so behaviour stays identical.
 */

import { AgentSession, AgentSessionStatus, useAgentStore } from '@llamatrade/core/stores/agent';
import { Plus, Search, Sparkles, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { CopilotConversation } from '../../components/agent/CopilotConversation';

const PAGE = 'copilot';
const DEFAULT_PROMPTS = [
  'Build a momentum rotation',
  'Why is Momentum Sectors down?',
  'Backtest my last idea',
  'Add a bond hedge',
];

/** Colored status dot per the design (active=orange, done=green, else gray). */
function statusDot(status: AgentSessionStatus): string {
  switch (status) {
    case AgentSessionStatus.ACTIVE:
      return 'bg-orange-500';
    case AgentSessionStatus.COMPLETED:
      return 'bg-green-600';
    default:
      return 'bg-ink/35';
  }
}

/** Relative age label ("2M" / "1H" / "3D" / "JUL 7"). */
function relativeAge(seconds?: bigint): string {
  if (!seconds) return '';
  const then = Number(seconds) * 1000;
  const diffMin = Math.max(0, Math.floor((Date.now() - then) / 60000));
  if (diffMin < 60) return `${diffMin || 1}m`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD}d`;
  return new Date(then).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** Bucket sessions into Today / Yesterday / Earlier by last-activity date. */
function ageGroup(seconds?: bigint): 'Today' | 'Yesterday' | 'Earlier' {
  if (!seconds) return 'Earlier';
  const d = new Date(Number(seconds) * 1000);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  if (t >= startOfToday) return 'Today';
  if (t >= startOfToday - 86400000) return 'Yesterday';
  return 'Earlier';
}

const GROUP_ORDER: Array<'Today' | 'Yesterday' | 'Earlier'> = ['Today', 'Yesterday', 'Earlier'];

export default function CopilotPage() {
  const {
    messages,
    pendingArtifacts,
    pendingArtifactIdsForCurrentMessage,
    sessions,
    currentSessionId,
    serviceUnavailable,
    loadSessions,
    selectSession,
    deleteSession,
    startNewChat,
  } = useAgentStore();

  const [search, setSearch] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Header subtitle mirrors whether a strategy draft is mid-flight.
  const inFlightArtifacts = useMemo(
    () => pendingArtifacts.filter((a) => pendingArtifactIdsForCurrentMessage.includes(a.id)),
    [pendingArtifacts, pendingArtifactIdsForCurrentMessage]
  );
  const unlinkedArtifacts = useMemo(() => {
    const linked = new Set<string>();
    for (const m of messages) for (const id of m.inlineArtifactIds ?? []) linked.add(id);
    const inFlight = new Set(pendingArtifactIdsForCurrentMessage);
    return pendingArtifacts.filter((a) => !linked.has(a.id) && !inFlight.has(a.id));
  }, [messages, pendingArtifacts, pendingArtifactIdsForCurrentMessage]);

  const filteredSessions = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = q ? sessions.filter((s) => s.title.toLowerCase().includes(q)) : sessions;
    const groups = new Map<string, AgentSession[]>();
    for (const s of list) {
      const g = ageGroup(s.lastActivityAt?.seconds);
      const arr = groups.get(g) ?? [];
      arr.push(s);
      groups.set(g, arr);
    }
    return groups;
  }, [sessions, search]);

  const activeSession = sessions.find((s) => s.id === currentSessionId);
  const headerTitle = activeSession?.title || 'New conversation';
  const headerSubtitle =
    messages.length === 0
      ? 'start a new conversation'
      : inFlightArtifacts.length || unlinkedArtifacts.length
        ? 'strategy draft in progress'
        : `${messages.length} messages`;

  return (
    <div className="flex h-[calc(100vh-56px)] bg-bone">
      {/* ---- History sidebar ---- */}
      <aside className="flex w-[280px] flex-none flex-col border-r-2 border-ink bg-paper">
        <div className="flex items-center justify-between border-b-2 border-ink px-4 py-3.5">
          <span className="flex items-center gap-1.5 font-display text-xl uppercase tracking-tight text-ink">
            <span className="text-orange-500">✦</span> Copilot
          </span>
          <button
            onClick={startNewChat}
            className="flex items-center gap-1.5 border-2 border-ink bg-orange-500 px-2.5 py-1.5 font-mono text-[10.5px] font-bold uppercase tracking-[0.04em] text-ink shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-y-0.5"
          >
            <Plus className="h-3 w-3" strokeWidth={3} />
            New
          </button>
        </div>

        <div className="mx-3.5 mb-1.5 mt-3 flex items-center gap-2 border-2 border-ink bg-bone px-2.5 py-2">
          <Search className="h-3 w-3 text-ink/50" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations…"
            className="flex-1 bg-transparent font-mono text-[11px] text-ink placeholder-ink/45 focus:outline-none"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-4">
          {sessions.length === 0 && (
            <p className="px-2 py-6 font-mono text-[10px] uppercase tracking-[0.08em] text-ink/40">
              {serviceUnavailable ? 'Copilot service offline' : 'No conversations yet'}
            </p>
          )}

          {GROUP_ORDER.map((group) => {
            const rows = filteredSessions.get(group);
            if (!rows || rows.length === 0) return null;
            return (
              <div key={group}>
                <div className="px-1.5 pb-1.5 pt-3 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-ink/40">
                  {group}
                </div>
                {rows.map((s) => {
                  const on = s.id === currentSessionId;
                  const confirming = confirmDeleteId === s.id;
                  return (
                    <div
                      key={s.id}
                      className={`group relative mb-0.5 border-2 transition-colors ${
                        on
                          ? 'border-ink bg-bone shadow-[inset_3px_0_0_rgb(var(--lt-orange-500)),3px_3px_0_rgb(var(--lt-ink))]'
                          : 'border-transparent hover:border-line'
                      }`}
                    >
                      <button
                        onClick={() => selectSession(s.id)}
                        className="flex w-full flex-col gap-1 px-2.5 py-2 pr-8 text-left"
                      >
                        <span className="flex items-center gap-2 text-[12.5px] font-bold leading-tight text-ink">
                          <span className={`h-2 w-2 flex-none border-[1.5px] border-ink ${statusDot(s.status)}`} />
                          <span className="truncate">{s.title || 'Untitled'}</span>
                        </span>
                        <span className="pl-4 font-mono text-[9.5px] uppercase tracking-[0.03em] text-ink/45">
                          {s.messageCount} msgs · {relativeAge(s.lastActivityAt?.seconds)}
                        </span>
                      </button>

                      {confirming ? (
                        <div className="absolute right-1 top-1 flex items-center gap-1.5 border-2 border-ink bg-paper px-1.5 py-1 shadow-[2px_2px_0_rgb(var(--lt-ink))]">
                          <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.04em] text-ink/60">
                            Delete?
                          </span>
                          <button
                            onClick={() => {
                              deleteSession(s.id);
                              setConfirmDeleteId(null);
                            }}
                            className="font-mono text-[8.5px] font-bold uppercase tracking-[0.04em] text-red-600 hover:underline"
                          >
                            Yes
                          </button>
                          <button
                            onClick={() => setConfirmDeleteId(null)}
                            className="font-mono text-[8.5px] font-bold uppercase tracking-[0.04em] text-ink/50 hover:underline"
                          >
                            No
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setConfirmDeleteId(s.id)}
                          aria-label="Delete conversation"
                          title="Delete conversation"
                          className="absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center border-2 border-transparent text-ink/40 opacity-0 transition-opacity hover:border-ink hover:bg-paper hover:text-red-600 focus:opacity-100 group-hover:opacity-100"
                        >
                          <Trash2 className="h-3 w-3" strokeWidth={2.5} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </aside>

      {/* ---- Chat ---- */}
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-none items-center justify-between border-b-2 border-ink bg-paper/60 px-6 py-3">
          <div className="min-w-0 font-mono text-[11px] font-bold uppercase tracking-[0.08em]">
            <span className="text-ink">{headerTitle}</span>{' '}
            <span className="text-ink/45">· {headerSubtitle}</span>
          </div>
          <div className="flex flex-none items-center gap-2">
            <span className="border-2 border-ink bg-bone px-2 py-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] text-ink">
              Paper
            </span>
            <span className="border-2 border-ink bg-paper px-2 py-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] text-ink">
              Real DSL
            </span>
            <span className="border-2 border-ink bg-ink px-2 py-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] text-bone">
              Copilot ✦
            </span>
          </div>
        </div>

        <CopilotConversation
          variant="page"
          page={PAGE}
          consumeSeed
          gridBackdrop
          fallbackPrompts={DEFAULT_PROMPTS}
          footerNote="Copilot writes real DSL · runs on your paper account"
          emptyState={
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="grid h-16 w-16 place-items-center border-2 border-ink bg-orange-500 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
                <Sparkles className="h-8 w-8 text-ink" />
              </div>
              <h2 className="mt-5 font-display text-2xl uppercase tracking-tight text-ink">
                LlamaTrade Copilot
              </h2>
              <p className="mt-2 max-w-md text-sm text-ink/60">
                Describe, build, edit, or explain a strategy. Copilot writes real DSL and runs it on
                your paper account.
              </p>
            </div>
          }
        />
      </main>
    </div>
  );
}
