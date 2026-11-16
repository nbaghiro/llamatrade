import type { SessionCommand } from '@llamatrade/core/stores/trading';
import { AlertTriangle, Check, Clock, Pause, Play, Square } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { SessionState, SessionStateView } from '../../lib/sessionState';
import { Dialog } from '../ui/Dialog';
import { StatusMark } from '../ui/StatusMark';

const REASON_ICON: Record<SessionState, typeof Check> = {
  running: Check,
  starting: Clock,
  paused: Pause,
  frozen: AlertTriangle,
  stopped: Square,
  error: AlertTriangle,
};

interface SessionHeaderProps {
  name: string;
  meta: ReactNode;
  state: SessionState;
  view: SessionStateView;
  /** Replaces the generic reason, e.g. the execution's error message. */
  reason?: string;
  /** A fact for the right of the reason band. */
  aside?: ReactNode;
  strategyId: string;
  pending: SessionCommand | null;
  onCommand: (command: SessionCommand) => void;
}

/** The session header: the state mark, the action the state calls for, and the reason under it. */
export function SessionHeader({
  name,
  meta,
  state,
  view,
  reason,
  aside,
  strategyId,
  pending,
  onCommand,
}: SessionHeaderProps) {
  const [confirmStop, setConfirmStop] = useState(false);
  const Icon = REASON_ICON[state];
  const attention = view.attention;

  return (
    <section
      aria-label={`${name}, ${view.label}`}
      className={`overflow-hidden rounded-panel border bg-panel ${attention ? 'border-risk-line' : 'border-line'}`}
    >
      <div className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="min-w-0">
          <h1 className="m-0 font-sans text-[15px] font-semibold tracking-normal">{name}</h1>
          <div className="mt-0.5 text-[11.5px] text-fg-3">{meta}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusMark state={view.mark} label={view.label} className="mr-1 text-[13.5px]" />
          {view.actions.includes('pause') && (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={pending !== null}
              onClick={() => onCommand('pause')}
            >
              <Pause className="h-3.5 w-3.5" aria-hidden="true" />
              {pending === 'pause' ? 'Pausing…' : 'Pause'}
            </button>
          )}
          {view.actions.includes('resume') && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={pending !== null}
              onClick={() => onCommand('resume')}
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              {pending === 'resume' ? 'Resuming…' : 'Resume'}
            </button>
          )}
          {view.actions.includes('stop') && (
            <button
              type="button"
              className={`btn ${state === 'frozen' ? 'btn-danger' : 'btn-secondary'}`}
              disabled={pending !== null}
              onClick={() => setConfirmStop(true)}
            >
              <Square className="h-3.5 w-3.5" aria-hidden="true" />
              {pending === 'stop' ? 'Stopping…' : 'Stop session'}
            </button>
          )}
          {view.actions.length === 0 && (
            <Link to={`/backtest?strategy=${strategyId}`} className="btn btn-secondary">
              Backtest it again
            </Link>
          )}
        </div>
      </div>
      <div
        className={`flex items-center gap-2.5 border-t border-line px-5 py-[11px] text-[12.5px] ${
          attention ? 'bg-risk-soft text-fg' : 'bg-canvas text-fg-2'
        }`}
      >
        <Icon
          className={`h-4 w-4 flex-none ${attention ? 'text-risk' : 'text-fg-3'}`}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1">{reason || view.reason}</span>
        {aside && <span className="num whitespace-nowrap text-fg-3">{aside}</span>}
      </div>
      <Dialog
        open={confirmStop}
        onClose={() => setConfirmStop(false)}
        title={`Stop ${name}?`}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setConfirmStop(false)}
            >
              Keep it running
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                setConfirmStop(false);
                onCommand('stop');
              }}
            >
              Stop session
            </button>
          </>
        }
      >
        <p className="m-0 text-[13px] text-fg-2">
          The session stops evaluating and places no new orders. Stopping can&apos;t be undone; to
          trade this strategy again, deploy it as a new session.
        </p>
      </Dialog>
    </section>
  );
}
