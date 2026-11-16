import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { ChevronRight, Code2, LayoutTemplate, Sparkles } from 'lucide-react';
import { useEffect, useState, type ComponentType } from 'react';
import { useNavigate } from 'react-router-dom';

import { PREFERRED_TEMPLATE_ID, rankTemplates } from '../../components/home/templates';
import { copilotUrl } from '../../lib/palette';
import { listTemplates } from '../../services/strategy';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

import { OnboardingLayout, StepTitle } from './OnboardingLayout';

type Route = 'template' | 'describe' | 'blank';

interface Choice {
  key: Route;
  title: string;
  body: string;
  short: string;
  Icon: ComponentType<{ className?: string }>;
}

function templateBody(templates: StrategyTemplate[] | null): { body: string; short: string } {
  const preferred = templates?.find((t) => t.id === PREFERRED_TEMPLATE_ID);
  const first = preferred ? `${preferred.name} is a simple first one.` : '';
  const count = templates?.length
    ? `${templates.length} to choose from.`
    : 'Ready-made strategies.';
  return { body: [count, first].filter(Boolean).join(' '), short: first || count };
}

/** /welcome: choose a way to start. Each route reaches a backtest before any broker ask. */
export default function WelcomePage() {
  const navigate = useNavigate();
  const createNew = useStrategyBuilderStore((s) => s.createNew);
  const [templates, setTemplates] = useState<StrategyTemplate[] | null>(null);
  const [route, setRoute] = useState<Route>('template');
  const [idea, setIdea] = useState('');

  useEffect(() => {
    let live = true;
    listTemplates()
      .then((r) => {
        if (live) setTemplates(rankTemplates(r.templates));
      })
      .catch(() => {
        if (live) setTemplates([]);
      });
    return () => {
      live = false;
    };
  }, []);

  const tpl = templateBody(templates);
  const choices: Choice[] = [
    { key: 'template', title: 'Start from a template', Icon: LayoutTemplate, ...tpl },
    {
      key: 'describe',
      title: 'Describe it in a sentence',
      body: 'Copilot turns it into a draft you can read before it runs.',
      short: 'Copilot writes a draft.',
      Icon: Sparkles,
    },
    {
      key: 'blank',
      title: 'Write it yourself',
      body: 'Open the editor with blocks or code.',
      short: 'Blocks or code.',
      Icon: Code2,
    },
  ];

  const onContinue = () => {
    if (route === 'template') {
      const first = templates?.[0]?.id ?? PREFERRED_TEMPLATE_ID;
      navigate(`/welcome/template/${encodeURIComponent(first)}`);
    } else if (route === 'describe') {
      navigate(copilotUrl(idea));
    } else {
      createNew();
      navigate('/strategies/builder');
    }
  };

  return (
    <OnboardingLayout step={1}>
      <StepTitle
        title="How would you like to start?"
        lead="Backtests don't need a broker, so you'll see a result before anything asks for Alpaca."
      />
      <div
        role="radiogroup"
        aria-label="How to start"
        className="my-1 grid w-full max-w-[808px] gap-2.5 md:grid-cols-3 md:gap-3.5"
      >
        {choices.map((c) => {
          const on = route === c.key;
          return (
            <button
              key={c.key}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setRoute(c.key)}
              className={`relative flex items-center gap-3 rounded-[10px] border bg-panel px-3.5 py-[13px] text-left transition-colors md:grid md:min-h-[170px] md:content-start md:gap-1.5 md:rounded-[12px] md:p-[18px] ${
                on
                  ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]'
                  : 'border-line-strong hover:border-fg-3'
              }`}
            >
              <span className="grid h-[34px] w-[34px] flex-none place-items-center rounded-[9px] bg-sunk text-accent">
                <c.Icon className="h-[18px] w-[18px]" />
              </span>
              <span className="min-w-0 flex-1 md:contents">
                <b className="block text-[13.5px] font-semibold md:mt-1.5 md:text-[14px]">
                  {c.title}
                </b>
                <span className="block text-[12.5px] text-fg-2 md:hidden">{c.short}</span>
                <span className="hidden text-[12.5px] text-fg-2 md:block">{c.body}</span>
              </span>
              <ChevronRight aria-hidden="true" className="h-4 w-4 flex-none text-fg-3 md:hidden" />
              <span
                aria-hidden="true"
                className={`absolute right-4 top-4 hidden h-4 w-4 rounded-full md:block ${
                  on ? 'border-[5px] border-accent-fill' : 'border-[1.5px] border-line-strong'
                }`}
              />
            </button>
          );
        })}
      </div>
      {route === 'describe' && (
        <div className="grid w-full max-w-[560px] gap-1.5">
          <label htmlFor="idea" className="text-[12px] font-medium text-fg-2">
            Your strategy in a sentence
          </label>
          <textarea
            id="idea"
            rows={2}
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            className="input h-auto py-2"
            placeholder="For example: hold bonds when SPY is overbought, otherwise the strongest sector fund."
          />
        </div>
      )}
      <button
        type="button"
        onClick={onContinue}
        className="btn btn-primary btn-lg w-full md:w-auto"
      >
        Continue
      </button>
    </OnboardingLayout>
  );
}
