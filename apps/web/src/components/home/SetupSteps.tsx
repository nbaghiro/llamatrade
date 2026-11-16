import { Check, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { SetupProgress, SetupStep, SetupStepKey } from '../../store/onboarding';

interface StepCopy {
  title: string;
  body: string;
  action: string;
  href: string;
}

const COPY: Record<SetupStepKey, StepCopy> = {
  strategy: {
    title: 'Choose a strategy',
    body: 'Start from a template or describe one in a sentence.',
    action: 'Browse templates',
    href: '/welcome',
  },
  backtest: {
    title: 'Backtest it',
    body: 'See how it would have done over past prices.',
    action: 'Run a backtest',
    href: '/backtest',
  },
  connect: {
    title: 'Connect Alpaca paper',
    body: 'Needed only to run it. You can do this at any time.',
    action: 'Connect',
    href: '/connect/alpaca?next=/dashboard',
  },
  deploy: {
    title: 'Deploy to paper',
    body: 'Run it in a paper session on your own account.',
    action: 'Deploy',
    href: '/strategies',
  },
};

/** Connect is open at any time; the other steps offer their action only when they're next. */
function showsAction(step: SetupStep): boolean {
  return !step.done && (step.current || step.key === 'connect');
}

function Marker({ step, index }: { step: SetupStep; index: number }) {
  const tone = step.done
    ? 'bg-accent-soft text-accent'
    : step.current
      ? 'bg-accent-fill text-accent-ink'
      : 'bg-sunk text-fg-3';
  return (
    <i
      aria-hidden="true"
      className={`grid h-6 w-6 flex-none place-items-center rounded-full font-mono text-[11px] font-semibold not-italic ${tone}`}
    >
      {step.done ? <Check className="h-3.5 w-3.5" /> : index + 1}
    </i>
  );
}

interface SetupStepsProps {
  progress: SetupProgress;
  onHide: () => void;
}

/** Four steps to a first paper session, shown on Home in place of the account figures. */
export function SetupSteps({ progress, onHide }: SetupStepsProps) {
  const { steps, doneCount } = progress;
  return (
    <section
      aria-label="Get to your first paper session"
      className="overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-2.5 text-[12.5px]">
        <b className="font-semibold">
          <span className="md:hidden">Your first paper session</span>
          <span className="hidden md:inline">Get to your first paper session</span>
        </b>
        <span className="flex items-center gap-3 text-fg-3">
          <span className="num">
            {doneCount} of {steps.length} done
          </span>
          <button type="button" onClick={onHide} className="btn btn-ghost btn-sm">
            Hide
          </button>
        </span>
      </div>

      <ol className="m-0 hidden list-none grid-cols-4 p-0 md:grid">
        {steps.map((step, i) => {
          const copy = COPY[step.key];
          return (
            <li
              key={step.key}
              aria-current={step.current ? 'step' : undefined}
              className={`grid content-start gap-1.5 border-r border-line p-3.5 text-[12.5px] last:border-r-0 ${
                step.current ? 'bg-accent-soft' : ''
              }`}
            >
              <Marker step={step} index={i} />
              <b className={`text-[13.5px] font-semibold ${step.done ? 'text-fg-2' : 'text-fg'}`}>
                {copy.title}
              </b>
              <span className="text-fg-2">{step.done ? 'Done.' : copy.body}</span>
              {showsAction(step) && (
                <Link
                  to={copy.href}
                  className={`btn mt-1 justify-self-start ${step.current ? 'btn-primary' : 'btn-secondary'}`}
                >
                  {copy.action}
                </Link>
              )}
            </li>
          );
        })}
      </ol>

      <ol className="m-0 grid list-none gap-0.5 px-4 py-2.5 md:hidden">
        {steps.map((step, i) => {
          const copy = COPY[step.key];
          const row = (
            <>
              <Marker step={step} index={i} />
              <span className="flex-1">{copy.title}</span>
              {showsAction(step) && (
                <ChevronRight aria-hidden="true" className="h-4 w-4 text-fg-3" />
              )}
            </>
          );
          const cls = `flex items-center gap-2.5 py-[9px] text-[14.5px] ${
            step.current ? 'text-fg' : 'text-fg-2'
          }`;
          return (
            <li key={step.key} aria-current={step.current ? 'step' : undefined}>
              {showsAction(step) ? (
                <Link to={copy.href} className={cls}>
                  {row}
                </Link>
              ) : (
                <span className={cls}>{row}</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
