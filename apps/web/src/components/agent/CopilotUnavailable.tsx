import { useAgentStore } from '@llamatrade/core/stores/agent';
import {
  Activity,
  ChevronRight,
  Clock,
  History,
  Layers,
  LayoutGrid,
  LineChart,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useCopilotSubject } from './subjectStore';

const ET_TIME = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/New_York',
});

interface Alternative {
  href: string;
  icon: ReactNode;
  title: string;
  sub: string;
}

/**
 * Copilot can't be reached and a question was kept (limits B): the question as an unsent draft,
 * and beside it the pages that answer the same need without the model.
 */
export function CopilotUnavailable({
  onRetry,
  historyHref = '/copilot?view=history',
  compact = false,
}: {
  onRetry: (text: string) => void;
  historyHref?: string;
  compact?: boolean;
}) {
  const unsent = useCopilotSubject((s) => s.unsent);
  const subject = useCopilotSubject((s) => s.subject);
  const setUnsent = useCopilotSubject((s) => s.setUnsent);
  if (!unsent) return null;

  const edit = () => {
    useAgentStore.setState({ seedPrompt: unsent.text, serviceUnavailable: false });
    setUnsent(null);
  };

  const alternatives: Alternative[] = [
    ...(subject && subject.kind !== 'account'
      ? [
          {
            href: subject.href,
            icon: <Activity className="h-4 w-4" />,
            title: subject.name,
            sub:
              subject.kind === 'session'
                ? 'Holdings, orders and the next rebalance'
                : subject.kind === 'backtest'
                  ? 'The full result, trades and months'
                  : 'Rules, versions and backtests',
          },
        ]
      : []),
    {
      href: '/strategies/builder',
      icon: <LayoutGrid className="h-4 w-4" />,
      title: 'Build from blocks',
      sub: "The builder doesn't need Copilot",
    },
    {
      href: '/strategies/templates',
      icon: <Layers className="h-4 w-4" />,
      title: 'Start from a template',
      sub: 'Templates with their backtests',
    },
    {
      href: '/backtest',
      icon: <LineChart className="h-4 w-4" />,
      title: 'Run a backtest',
      sub: 'Any strategy or draft',
    },
    {
      href: historyHref,
      icon: <History className="h-4 w-4" />,
      title: 'Past conversations',
      sub: 'Readable as usual',
    },
  ];

  return (
    <div className={`grid gap-8 ${compact ? '' : 'lg:grid-cols-[minmax(0,1fr)_380px]'}`}>
      <section className="grid content-start gap-3">
        <h2 className="m-0 text-[18px] font-semibold">Your question</h2>
        <div className="rounded-[10px] border border-dashed border-line-strong bg-sunk px-4 py-3.5">
          <p className="m-0 whitespace-pre-wrap text-[14px]">{unsent.text}</p>
          <span className="mt-2 flex items-center gap-1.5 text-[12px] text-fg-3">
            <Clock className="h-3.5 w-3.5" />
            Kept {ET_TIME.format(unsent.at)} · not sent
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-primary" onClick={() => onRetry(unsent.text)}>
            Try now
          </button>
          <button type="button" className="btn btn-ghost" onClick={edit}>
            Edit
          </button>
        </div>
        <p className="m-0 text-[12.5px] text-fg-3">
          Nothing was sent. Try again when Copilot is back, or use the pages beside this, which read
          your records directly.
        </p>
      </section>
      <section className="grid content-start gap-3">
        <h2 className="m-0 text-[15px] font-semibold">These work without Copilot</h2>
        <ul className="panel m-0 list-none px-4 py-1">
          {alternatives.map((a) => (
            <li key={a.href} className="border-b border-line last:border-0">
              <Link to={a.href} className="group flex items-center gap-3 py-3">
                <span className="text-fg-3">{a.icon}</span>
                <span className="grid min-w-0 flex-1">
                  <b className="text-[13.5px] font-medium group-hover:text-accent">{a.title}</b>
                  <span className="text-[12.5px] text-fg-3">{a.sub}</span>
                </span>
                <ChevronRight className="h-4 w-4 flex-none text-fg-3" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
