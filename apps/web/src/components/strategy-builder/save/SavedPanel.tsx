import { CheckCircle2, LineChart, Pencil, Repeat2, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface SavedInfo {
  version: number;
  note: string;
  /** True when the note was written from the change list rather than typed. */
  noteWritten: boolean;
  at: Date;
}

interface SavedPanelProps {
  saved: SavedInfo;
  /** "Nov 2024 to Nov 2026, $10,000, SPY. Same as version 3's last run." */
  backtestLine: string;
  onBacktest: () => void;
  onClose: () => void;
  session: { id: string; name: string; version: number | null } | null;
}

const clock = (d: Date) => d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

function Next({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[18px_minmax(0,1fr)_auto] items-start gap-3 border-t border-line py-3 first:border-t-0">
      <span className="mt-0.5 text-fg-3">{icon}</span>
      <span className="grid gap-0.5">
        <b className="text-[13px] font-medium text-fg">{title}</b>
        <span className="text-[12.5px] text-fg-2">{text}</span>
      </span>
      {action}
    </div>
  );
}

/** save2 A: what the save left behind, and the three things people do next. */
export function SavedPanel({ saved, backtestLine, onBacktest, onClose, session }: SavedPanelProps) {
  const prev = saved.version - 1;
  return (
    <section aria-label={`Saved as version ${saved.version}`} className="panel panel-rim">
      <header className="flex items-center gap-2.5 border-b border-line px-5 py-3">
        <CheckCircle2 className="h-4 w-4 text-accent" aria-hidden="true" />
        <h3 className="m-0 text-[13.5px] font-semibold text-fg">
          Saved as version {saved.version}
        </h3>
        <span className="ml-auto font-mono text-[12px] text-fg-3">{clock(saved.at)}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="grid h-6 w-6 place-items-center rounded-[5px] text-fg-3 hover:bg-sunk hover:text-fg"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </header>
      <div className="grid gap-4 px-5 py-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] md:gap-8">
        <div className="grid content-start gap-1.5">
          <span className="kicker">Note</span>
          <p className="m-0 text-[13.5px] text-fg">{saved.note || 'No note.'}</p>
          <p className="m-0 text-[12px] text-fg-3">
            {saved.noteWritten && saved.note ? 'Written from the changes. ' : ''}
            {prev > 0
              ? `Version ${prev}${session ? ' and its paper session are' : ' is'} unchanged.`
              : 'Nothing trades until you start a session.'}
          </p>
        </div>
        <div>
          <span className="kicker">What next</span>
          <div className="mt-1">
            <Next
              icon={<LineChart className="h-4 w-4" />}
              title={`Backtest version ${saved.version}`}
              text={backtestLine}
              action={
                <button type="button" onClick={onBacktest} className="btn btn-primary btn-sm">
                  Run
                </button>
              }
            />
            <Next
              icon={<Pencil className="h-4 w-4" />}
              title="Keep editing"
              text={`Changes from here start a version ${saved.version + 1} draft.`}
            />
            {session && (
              <Next
                icon={<Repeat2 className="h-4 w-4" />}
                title="Switch the paper session"
                text={`${session.name} runs version ${session.version ?? prev}. Switch from the session page when you’re ready.`}
                action={
                  <Link to={`/trading/${session.id}`} className="btn btn-secondary btn-sm">
                    Open
                  </Link>
                }
              />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
