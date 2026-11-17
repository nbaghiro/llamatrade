/**
 * The Copilot side panel for a quick question from any page. It shares the conversation with
 * /copilot through the agent store, so expanding it continues the same thread on the full page.
 */

import { useAgentStore } from '@llamatrade/core/stores/agent';
import { Maximize2, Plus, X } from 'lucide-react';
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useMediaQuery } from '../strategies/useMediaQuery';

import { CopilotConversation } from './CopilotConversation';
import { CopilotUnavailable } from './CopilotUnavailable';
import { askPlaceholder } from './subjects';
import { useCopilotSubject } from './subjectStore';
import { useCopilotSend } from './useCopilotSend';
import { useRouteSubject } from './useRouteSubject';

const MIN_WIDTH = 400;
const MAX_WIDTH = 760;
const DEFAULT_WIDTH = 460;
const WIDTH_KEY = 'copilot-panel-width';

function loadWidth(): number {
  try {
    const saved = Number(localStorage.getItem(WIDTH_KEY));
    return saved >= MIN_WIDTH && saved <= MAX_WIDTH ? saved : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

function pageContext(pathname: string): string {
  const first = pathname.split('/')[1] ?? '';
  return first || 'app';
}

export function CopilotSidePanel() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { sessions, currentSessionId, panelOpen, closePanel, loadSessions, startNewChat } =
    useAgentStore();
  const [width, setWidth] = useState(loadWidth);
  const [full, setFull] = useState(false);
  const phone = useMediaQuery('(max-width: 767px)');
  const dragFrom = useRef<number | null>(null);
  const routeSubject = useRouteSubject(pathname);
  const setSubject = useCopilotSubject((s) => s.setSubject);
  const send = useCopilotSend(pageContext(pathname));

  useEffect(() => {
    if (panelOpen) setSubject(routeSubject);
    // The subject follows the page only when the panel opens or the page changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelOpen, routeSubject?.key]);

  useEffect(() => {
    if (!panelOpen) setFull(false);
  }, [panelOpen]);

  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      // Width is a convenience; a blocked store keeps the default next time.
    }
  }, [width]);

  useEffect(() => {
    if (panelOpen) loadSessions();
  }, [panelOpen, loadSessions]);

  useEffect(() => {
    if (panelOpen && pathname.startsWith('/copilot')) closePanel();
  }, [panelOpen, pathname, closePanel]);

  useEffect(() => {
    if (!panelOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closePanel();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [panelOpen, closePanel]);

  if (!panelOpen) return null;

  const startResize = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const max = Math.min(MAX_WIDTH, window.innerWidth - 80);
    const onMove = (ev: PointerEvent) =>
      setWidth(Math.min(max, Math.max(MIN_WIDTH, window.innerWidth - ev.clientX)));
    const onUp = () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
    };
    document.body.style.userSelect = 'none';
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  };

  const expand = () => {
    closePanel();
    navigate(currentSessionId ? `/copilot/${currentSessionId}` : '/copilot');
  };

  const title = sessions.find((s) => s.id === currentSessionId)?.title || 'New conversation';

  return (
    <aside
      role="dialog"
      aria-label="Copilot"
      style={{ ['--panel-w' as string]: `${width}px` }}
      className={`fixed inset-x-0 bottom-0 z-50 flex flex-col border-line-strong bg-panel shadow-xl max-md:rounded-t-[16px] max-md:border-t md:left-auto md:top-14 md:w-[var(--panel-w)] md:border-l ${
        full ? 'top-14' : 'top-[42dvh]'
      }`}
    >
      <button
        type="button"
        aria-label={full ? 'Lower the sheet' : 'Raise the sheet to full height'}
        onClick={() => setFull(!full)}
        onPointerDown={(e) => {
          dragFrom.current = e.clientY;
        }}
        onPointerUp={(e) => {
          if (dragFrom.current === null) return;
          const moved = e.clientY - dragFrom.current;
          dragFrom.current = null;
          if (moved < -24) setFull(true);
          else if (moved > 24) {
            if (full) setFull(false);
            else closePanel();
          }
        }}
        className="grid h-5 flex-none touch-none place-items-center md:hidden"
      >
        <span className="h-1 w-10 rounded-full bg-line-strong" />
      </button>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the Copilot panel"
        onPointerDown={startResize}
        className="absolute -left-1 bottom-0 top-0 z-10 hidden w-2 cursor-col-resize md:block"
      />
      <div className="flex flex-none items-center gap-2 border-b border-line py-2.5 pl-4 pr-2">
        <div className="min-w-0 flex-1">
          <span className="kicker block">Copilot</span>
          <b className="block truncate text-[13.5px] font-semibold">{title}</b>
        </div>
        <button
          type="button"
          onClick={startNewChat}
          aria-label="New conversation"
          title="New conversation"
          className="btn btn-ghost px-2"
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={expand}
          aria-label="Open on the full page"
          title="Open on the full page"
          className="btn btn-ghost px-2"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={closePanel}
          aria-label="Close"
          title="Close"
          className="btn btn-ghost px-2"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <CopilotConversation
        variant="panel"
        page={pageContext(pathname)}
        placeholder={routeSubject ? askPlaceholder(routeSubject) : 'Ask Copilot about this page'}
        folded={phone && !full}
        unavailableView={<CopilotUnavailable onRetry={send} compact />}
        emptyState={
          <div className="grid gap-1.5 py-10 text-center">
            <h2 className="m-0 text-[15px] font-semibold">Ask a quick question</h2>
            <p className="m-0 text-[13px] text-fg-2">
              Build, edit or explain a strategy without leaving this page. Open the full page for
              longer work and your history.
            </p>
          </div>
        }
      />
    </aside>
  );
}
