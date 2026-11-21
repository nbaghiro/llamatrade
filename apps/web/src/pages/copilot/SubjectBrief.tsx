import { sessionWhen } from '@llamatrade/core/agent/history';
import type { AgentSession } from '@llamatrade/core/stores/agent';
import {
  ArrowRight,
  BarChart3,
  Clock,
  Code2,
  FlaskConical,
  HelpCircle,
  LineChart,
  List,
  Pencil,
  Wallet,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { ChatInput, SubjectChip } from '../../components/agent/ChatInput';
import { conversationPath } from '../../components/agent/entry';
import {
  askPlaceholder,
  earlierAbout,
  subjectLimits,
  subjectQuestions,
  subjectReads,
  type CopilotSubject,
  type QuestionIcon,
  type ReadIcon,
} from '../../components/agent/subjects';
import { dayLabel } from '../../components/sessions/sessionRows';
import { ModeBadge } from '../../components/ui';

const READ_ICON: Record<ReadIcon, ReactNode> = {
  code: <Code2 className="h-4 w-4" />,
  positions: <Wallet className="h-4 w-4" />,
  chart: <LineChart className="h-4 w-4" />,
  list: <List className="h-4 w-4" />,
  backtest: <BarChart3 className="h-4 w-4" />,
};

const QUESTION_ICON: Record<QuestionIcon, ReactNode> = {
  clock: <Clock className="h-4 w-4" />,
  why: <HelpCircle className="h-4 w-4" />,
  chart: <LineChart className="h-4 w-4" />,
  draft: <Pencil className="h-4 w-4" />,
  test: <FlaskConical className="h-4 w-4" />,
};

const OPEN_LABEL: Record<CopilotSubject['kind'], string> = {
  session: 'Open session',
  strategy: 'Open strategy',
  backtest: 'Open backtest',
  account: 'Open portfolio',
};

function subline(s: CopilotSubject): string {
  const parts: string[] = [];
  if (s.kind === 'account')
    return 'Your sessions, positions and performance across Alpaca accounts';
  if (s.version) parts.push(`Version ${s.version}`);
  if (s.kind === 'backtest') parts.push(s.meta ? `Finished ${s.meta}` : 'Backtest');
  if (s.rebalance) parts.push(`rebalances ${s.rebalance.toLowerCase()}`);
  if (s.next) parts.push(`next rebalance ${dayLabel(s.next)}`);
  return parts.join(' · ');
}

/** A chosen subject: what Copilot reads for it, questions for its state and a scoped composer. */
export function SubjectBrief({
  subject,
  sessions,
  onSend,
  onClear,
  disabled,
  busy,
  initialValue = '',
}: {
  subject: CopilotSubject;
  sessions: readonly AgentSession[];
  onSend: (text: string) => void;
  onClear: () => void;
  disabled: boolean;
  busy: boolean;
  initialValue?: string;
}) {
  const reads = subjectReads(subject);
  const questions = subjectQuestions(subject);
  const earlier = earlierAbout(sessions, subject);
  const state = subject.state ?? '';

  return (
    <div className="mx-auto grid w-full max-w-[1100px] gap-5 px-4 py-5 md:px-8 md:py-7">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] md:text-[26px]">
              {subject.name}
            </h1>
            {subject.mode && <ModeBadge mode={subject.mode} />}
            {state && (
              <span
                className={`flex items-center gap-1.5 text-[13px] ${subject.tone === 'risk' ? 'text-risk' : 'text-fg-2'}`}
              >
                <span
                  aria-hidden
                  className={`h-2 w-2 rounded-full ${subject.tone === 'risk' ? 'bg-risk' : subject.tone === 'accent' ? 'bg-accent' : 'bg-fg-3'}`}
                />
                {state}
              </span>
            )}
          </div>
          <p className="m-0 mt-1 text-[13.5px] text-fg-2">{subline(subject)}</p>
        </div>
        <Link to={subject.href} className="btn btn-secondary">
          {OPEN_LABEL[subject.kind]}
        </Link>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel flex flex-col">
          <div className="flex items-baseline justify-between border-b border-line px-4 py-3.5">
            <h2 className="m-0 text-[14px] font-semibold">What Copilot reads for this</h2>
            <span className="text-[12.5px] text-fg-3">
              {reads.length} {reads.length === 1 ? 'source' : 'sources'}
            </span>
          </div>
          <ul className="m-0 grid list-none px-4 py-1">
            {reads.map((r) => (
              <li
                key={r.label}
                className="flex items-center gap-3 border-b border-line py-2.5 text-[13.5px] last:border-0"
              >
                <span className="text-fg-3">{READ_ICON[r.icon]}</span>
                <span className="min-w-0 flex-1">{r.label}</span>
                <span className="hidden font-mono text-[11.5px] text-fg-3 sm:inline">{r.tool}</span>
              </li>
            ))}
          </ul>
          <p className="m-0 mt-auto border-t border-line px-4 py-3 text-[12.5px] text-fg-3">
            {subjectLimits(subject)}
          </p>
        </section>

        <section className="panel">
          <div className="flex items-baseline justify-between border-b border-line px-4 py-3.5">
            <h2 className="m-0 text-[14px] font-semibold">Questions for today</h2>
            <span className="text-[12.5px] text-fg-3">From its current state</span>
          </div>
          <ul className="m-0 grid list-none px-4 py-1">
            {questions.map((q) => (
              <li key={q.text} className="border-b border-line last:border-0">
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={() => onSend(q.text)}
                  className="group flex w-full items-center gap-3 py-2.5 text-left text-[13.5px] hover:text-accent disabled:opacity-50"
                >
                  <span className="text-fg-3">{QUESTION_ICON[q.icon]}</span>
                  <span className="min-w-0 flex-1">{q.text}</span>
                  <ArrowRight className="h-3.5 w-3.5 flex-none text-fg-3 group-hover:text-accent" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="max-md:sticky max-md:bottom-0 max-md:-mx-4 max-md:bg-canvas max-md:px-4 max-md:py-2">
        <ChatInput
          onSend={onSend}
          initialValue={initialValue}
          disabled={disabled}
          busy={busy}
          placeholder={askPlaceholder(subject)}
          hint="Copilot proposes, you confirm"
          chips={<SubjectChip label={subject.name} onRemove={onClear} />}
        />
      </div>

      {earlier.length > 0 && (
        <section>
          <div className="kicker mb-1.5">Earlier about {subject.strategyName ?? subject.name}</div>
          {earlier.map((s) => (
            <Link
              key={s.id}
              to={conversationPath(s.id)}
              className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 text-[13.5px] hover:text-accent"
            >
              <span className="min-w-0 truncate font-medium">{s.title || 'Untitled'}</span>
              <span className="flex-none font-mono text-[12px] text-fg-3">
                {sessionWhen(s.lastActivityAt?.seconds)}
              </span>
            </Link>
          ))}
        </section>
      )}
    </div>
  );
}
