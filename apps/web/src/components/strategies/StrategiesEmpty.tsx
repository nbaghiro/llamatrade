import { Link } from 'react-router-dom';

import { PanelError, Skeleton } from '../ui';

import { DescribeBox } from './DescribeBox';
import { TemplateCard } from './TemplateCard';
import { pickStarters } from './templateModel';
import { useStartDraft } from './useStartDraft';
import { useTemplates } from './useTemplates';

/** A new account's list: three starter templates with their holdings, and a line to describe one. */
export function StrategiesEmpty() {
  const templates = useTemplates();
  const { fromTemplate, describe } = useStartDraft();
  const total = templates.status === 'ready' ? templates.templates.length : null;

  return (
    <section className="panel grid justify-items-center px-4 pb-10 pt-9 text-center sm:px-8 sm:pb-12 sm:pt-11">
      <div className="grid w-full max-w-[860px] justify-items-center gap-6">
        <div className="grid justify-items-center gap-2">
          <h2 className="m-0 text-[22px] font-semibold tracking-[-0.015em] sm:text-[24px]">
            Start with a strategy
          </h2>
          <p className="m-0 max-w-[540px] text-[14px] text-fg-2">
            A strategy is a set of target weights and the rules that change them. Pick a template to
            see it as an outline and as code, then backtest it before anything runs.
          </p>
        </div>

        {templates.status === 'error' ? (
          <PanelError
            title="Templates couldn’t be loaded"
            cause="The strategy service didn’t answer."
            unaffected="You can still describe a strategy below."
            onRetry={templates.retry}
          />
        ) : (
          <div className="grid w-full gap-3.5 sm:grid-cols-3">
            {templates.status === 'loading'
              ? [0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="grid gap-3 rounded-panel border border-line bg-canvas p-4"
                    aria-hidden="true"
                  >
                    <Skeleton className="h-3 w-32" />
                    <Skeleton className="h-2.5 w-full" />
                    <Skeleton className="h-2 w-full" />
                  </div>
                ))
              : pickStarters(templates.templates).map((t) => (
                  <TemplateCard key={t.id} template={t} onUse={fromTemplate} />
                ))}
          </div>
        )}

        <div className="grid w-full gap-2.5 text-left">
          <DescribeBox
            onSubmit={describe}
            placeholder="Or describe one, for example “momentum across the 11 sector ETFs, monthly”"
          />
          <p className="m-0 text-center text-[12px] text-fg-3">
            Copilot writes a draft in the strategy language. Nothing is saved or run until you
            choose to.{' '}
            <Link to="/strategies/templates" className="text-accent hover:underline">
              {total ? `Browse all ${total} templates` : 'Browse all templates'}
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}
