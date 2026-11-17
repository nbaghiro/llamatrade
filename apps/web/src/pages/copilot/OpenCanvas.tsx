import { sessionWhen } from '@llamatrade/core/agent/history';
import type { AgentSession } from '@llamatrade/core/stores/agent';
import {
  ArrowRight,
  LineChart as ChartIcon,
  Info,
  PencilLine,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { ChatInput } from '../../components/agent/ChatInput';
import type { StarterGroup } from '../../components/agent/subjects';
import { LogoMark } from '../../components/common/Logo';
import { PageArt } from '../../components/ui';

const JOBS: Record<
  StarterGroup['label'],
  { title: string; icon: LucideIcon; does: string; gives: string }
> = {
  Explain: {
    title: 'Explain',
    icon: Info,
    does: 'Reads a session’s rules, positions and performance, and says why it holds what it holds.',
    gives: 'Gives you an answer with the records it used.',
  },
  Build: {
    title: 'Draft',
    icon: PencilLine,
    does: 'Turns a sentence into the strategy language. Drafts stay drafts until you save them.',
    gives: 'Gives you a draft to open in the builder.',
  },
  Test: {
    title: 'Test',
    icon: ChartIcon,
    does: 'Proposes backtests with dates and capital, and runs them when you approve.',
    gives: 'Gives you results labelled as backtests.',
  },
};

const ORDER: readonly StarterGroup['label'][] = ['Explain', 'Build', 'Test'];

/** Copilot with nothing chosen: what it can and can't do, around a large composer (page2 D). */
export function OpenCanvas({
  starters,
  last,
  onSend,
  disabled,
  busy,
  initialValue = '',
}: {
  starters: StarterGroup[];
  last: AgentSession | null;
  onSend: (text: string) => void;
  disabled: boolean;
  busy: boolean;
  initialValue?: string;
}) {
  const groups = ORDER.map((label) => starters.find((g) => g.label === label)).filter(
    (g): g is StarterGroup => g !== undefined
  );
  return (
    <div className="relative isolate overflow-hidden px-4 pb-12 pt-10 md:px-8 md:pt-16">
      <PageArt shape="copilot" />
      <div className="mx-auto grid max-w-[760px] justify-items-center gap-3 text-center">
        <LogoMark size={44} bold className="text-fg" />
        <h1 className="m-0 text-[28px] font-semibold tracking-[-0.03em] md:text-[40px]">
          Ask about your strategies
        </h1>
        <p className="m-0 max-w-[600px] text-[14.5px] leading-[1.6] text-fg-2 md:text-[15.5px]">
          Copilot reads your strategies, sessions and backtests, and answers with the records it
          used.
        </p>
      </div>
      <div className="mx-auto mt-7 max-w-[760px]">
        <ChatInput
          large
          onSend={onSend}
          initialValue={initialValue}
          disabled={disabled}
          busy={busy}
          placeholder="Describe a strategy, or ask about one you run"
        />
      </div>
      <div className="mx-auto mt-8 grid max-w-[970px] gap-4 md:grid-cols-3">
        {groups.map((g) => {
          const job = JOBS[g.label];
          const Icon = job.icon;
          return (
            <section key={g.label} className="panel flex flex-col px-5 pb-3 pt-4">
              <h2 className="m-0 flex items-center gap-2 text-[15px] font-semibold">
                <Icon className="h-4 w-4 text-accent" aria-hidden="true" />
                {job.title}
              </h2>
              <p className="m-0 mt-2.5 text-[13px] leading-[1.5] text-fg-2">{job.does}</p>
              <p className="m-0 mt-2.5 text-[12px] text-fg-3">{job.gives}</p>
              <div className="mt-auto pt-3">
                {g.prompts.map((p) => (
                  <button
                    key={p}
                    type="button"
                    disabled={disabled || busy}
                    onClick={() => onSend(p)}
                    className="group flex w-full items-start justify-between gap-3 border-t border-line py-2.5 text-left text-[13px] leading-[1.4] text-accent hover:underline disabled:opacity-50"
                  >
                    <span>{p}</span>
                    <ArrowRight className="mt-0.5 h-3.5 w-3.5 flex-none text-fg-3 group-hover:text-accent" />
                  </button>
                ))}
              </div>
            </section>
          );
        })}
      </div>
      <div className="panel mx-auto mt-4 flex max-w-[970px] items-start gap-3 px-5 py-3.5 text-[13.5px] leading-[1.5] text-fg-2">
        <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-fg-3" aria-hidden="true" />
        <p className="m-0">
          <b className="font-semibold text-fg">Copilot doesn’t place orders.</b> It can’t start,
          stop or change a session. You do that on the usual screens, where you confirm each step.
        </p>
      </div>
      {last && (
        <p className="m-0 mt-8 text-center text-[13px] text-fg-3">
          Last conversation: <span className="text-fg">{last.title || 'Untitled'}</span>,{' '}
          {sessionWhen(last.lastActivityAt?.seconds)} ·{' '}
          <Link to={`/copilot/${last.id}`} className="text-accent hover:underline">
            Continue
          </Link>
        </p>
      )}
    </div>
  );
}
