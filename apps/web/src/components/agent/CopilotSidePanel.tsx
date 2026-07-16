/**
 * Overlay side-panel Copilot ("quick ask" mode).
 *
 * A right-docked chat panel that floats over the current page behind a
 * translucent ink scrim. It shares ALL of its conversation state with the
 * full-page /copilot view via the agent store, so a conversation started here
 * continues seamlessly when "expanded". The thread + composer come from the
 * shared <CopilotConversation>; this file is just the dock shell (resize,
 * header, context strip).
 *
 * Opened by the floating action button (AgentFAB → togglePanel).
 */

import { Maximize2, Plus, Sparkles, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAgentStore } from '../../store/agent';

import { CopilotConversation } from './CopilotConversation';

const MIN_PANEL_WIDTH = 440;
const MAX_PANEL_WIDTH = 760;
const DEFAULT_PANEL_WIDTH = 480;
const PANEL_WIDTH_KEY = 'copilot-panel-width';
const DEFAULT_PROMPTS = ['Build a momentum rotation', 'Add a bond hedge', 'Backtest my last idea'];

function loadPanelWidth(): number {
  const saved = Number(localStorage.getItem(PANEL_WIDTH_KEY));
  return saved >= MIN_PANEL_WIDTH && saved <= MAX_PANEL_WIDTH ? saved : DEFAULT_PANEL_WIDTH;
}

/** Friendly label for the "On: …" context strip, derived from the route. */
function pageLabel(pathname: string): string {
  if (pathname.startsWith('/strategies/builder') || pathname.startsWith('/strategies/'))
    return 'Strategy Builder';
  if (pathname.startsWith('/strategies')) return 'Strategies';
  if (pathname.startsWith('/backtest')) return 'Backtest';
  if (pathname.startsWith('/portfolio')) return 'Portfolio';
  if (pathname.startsWith('/trading')) return 'Trading';
  if (pathname.startsWith('/dashboard')) return 'Dashboard';
  if (pathname.startsWith('/settings')) return 'Settings';
  if (pathname.startsWith('/billing')) return 'Billing';
  return 'LlamaTrade';
}

export function CopilotSidePanel() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    messages,
    pendingArtifacts,
    pendingArtifactIdsForCurrentMessage,
    sessions,
    currentSessionId,
    panelOpen,
    closePanel,
    loadSessions,
    startNewChat,
  } = useAgentStore();

  const page = pageLabel(location.pathname);

  // Drag-to-resize the docked width (persisted). The panel is right-anchored, so
  // width tracks the distance from the pointer to the right edge of the viewport.
  const [width, setWidth] = useState(loadPanelWidth);

  useEffect(() => {
    localStorage.setItem(PANEL_WIDTH_KEY, String(width));
  }, [width]);

  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const maxW = Math.min(MAX_PANEL_WIDTH, window.innerWidth - 80);
    const onMove = (ev: PointerEvent) => {
      setWidth(Math.min(maxW, Math.max(MIN_PANEL_WIDTH, window.innerWidth - ev.clientX)));
    };
    const onUp = () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  };

  // Lock background page scroll while the dock is open so the page behind can't
  // drift out of alignment. Compensate for the removed scrollbar to avoid a jump.
  useEffect(() => {
    if (!panelOpen) return;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    const prevOverflow = document.body.style.overflow;
    const prevPadding = document.body.style.paddingRight;
    document.body.style.overflow = 'hidden';
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = prevOverflow;
      document.body.style.paddingRight = prevPadding;
    };
  }, [panelOpen]);

  // Load history each time the panel opens (resolves the header title).
  useEffect(() => {
    if (panelOpen) loadSessions();
  }, [panelOpen, loadSessions]);

  // The full-page /copilot view owns this conversation; don't double-render.
  useEffect(() => {
    if (panelOpen && location.pathname === '/copilot') closePanel();
  }, [panelOpen, location.pathname, closePanel]);

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

  if (!panelOpen) return null;

  const activeSession = sessions.find((s) => s.id === currentSessionId);
  const headerTitle = activeSession?.title || 'New conversation';
  const headerSubtitle =
    messages.length === 0
      ? 'quick ask'
      : inFlightArtifacts.length || unlinkedArtifacts.length
        ? 'draft in progress'
        : `${messages.length} msgs`;

  // Carry the shared in-memory conversation into the full-page view; SPA
  // navigation keeps the store, so it continues there.
  const handleExpand = () => {
    closePanel();
    navigate('/copilot');
  };

  return (
    <aside
      role="dialog"
      aria-label="Copilot quick ask"
      style={{ width }}
      className="fixed right-0 top-14 z-50 flex h-[calc(100vh-56px)] flex-col border-l-2 border-ink bg-paper shadow-[-8px_0_0_rgb(var(--lt-orange-500)/0.16)]"
    >
      {/* Resize handle on the left edge (drag to widen/narrow). */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize Copilot panel"
        onPointerDown={startResize}
        className="group absolute -left-1.5 top-0 bottom-0 z-10 flex w-3 cursor-col-resize items-center justify-center"
      >
        <span className="h-14 w-1.5 border-2 border-ink bg-orange-500 shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-all group-hover:h-24" />
      </div>

      {/* Header. */}
      <div className="flex flex-none items-center gap-2.5 border-b-2 border-ink bg-ink py-3 pl-4 pr-3 text-bone">
        <Sparkles className="h-3.5 w-3.5 flex-none text-orange-500" />
        <div className="min-w-0 truncate font-mono text-[11px] font-bold uppercase tracking-[0.07em]">
          <span className="text-bone">{headerTitle}</span>{' '}
          <span className="text-bone/50">· {headerSubtitle}</span>
        </div>
        <div className="ml-auto flex flex-none items-center gap-1.5">
          <button
            type="button"
            onClick={startNewChat}
            title="New chat"
            className="grid h-7 w-7 place-items-center border-2 border-bone/30 text-bone transition-colors hover:border-bone"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.6} />
          </button>
          <button
            type="button"
            onClick={handleExpand}
            title="Expand to full page"
            className="grid h-7 w-7 place-items-center border-2 border-bone/30 text-bone transition-colors hover:border-bone"
          >
            <Maximize2 className="h-3.5 w-3.5" strokeWidth={2.2} />
          </button>
          <button
            type="button"
            onClick={closePanel}
            title="Close"
            className="grid h-7 w-7 place-items-center border-2 border-orange-500 bg-orange-500 text-ink transition-colors hover:bg-orange-600"
          >
            <X className="h-3.5 w-3.5" strokeWidth={2.6} />
          </button>
        </div>
      </div>

      {/* Context strip. */}
      <div className="flex flex-none items-center gap-2 border-b-2 border-ink bg-bone px-4 py-2 font-mono text-[9.5px] font-bold uppercase tracking-[0.05em] text-ink/60">
        <span className="h-1.5 w-1.5 flex-none bg-green-600" />
        <span className="truncate">On: {page}</span>
        <span className="ml-auto flex-none border-2 border-ink bg-paper px-1.5 py-0.5 text-[9px] text-ink">
          Paper
        </span>
      </div>

      <CopilotConversation
        variant="panel"
        page="copilot"
        fallbackPrompts={DEFAULT_PROMPTS}
        footerNote="Real DSL · paper account"
        placeholder="Ask Copilot to build, edit, or explain…"
        emptyState={
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="grid h-12 w-12 place-items-center border-2 border-ink bg-orange-500 shadow-[3px_3px_0_rgb(var(--lt-ink))]">
              <Sparkles className="h-6 w-6 text-ink" />
            </div>
            <h2 className="mt-4 font-display text-lg uppercase tracking-tight text-ink">
              Quick ask Copilot
            </h2>
            <p className="mt-2 max-w-[16rem] text-[13px] text-ink/60">
              Build, edit, or explain a strategy without leaving this page. Expand ↗ for deep work.
            </p>
          </div>
        }
      />
    </aside>
  );
}
