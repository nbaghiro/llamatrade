import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { ChevronRight, FlaskConical } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AccountPath } from '../../components/auth/AccountPath';
import {
  PREFERRED_TEMPLATE_ID,
  rankTemplates,
  templateMeta,
} from '../../components/home/templates';
import { Skeleton } from '../../components/ui';
import { copilotUrl } from '../../lib/palette';
import { listTemplates } from '../../services/strategy';
import { useAuthStore } from '../../store/auth';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

import { OnboardingLayout, StepTitle } from './OnboardingLayout';
import { startPath } from './startPath';

const EXAMPLE = 'Hold bonds and gold when the yield curve inverts, otherwise SPY. Check daily.';

function Door({
  title,
  body,
  preview,
  action,
}: {
  title: string;
  body: string;
  preview: ReactNode;
  action: ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className="grid grid-rows-[auto_1fr] overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="border-b border-line bg-sunk p-4 md:h-[190px]">{preview}</div>
      <div className="grid content-start gap-2 p-4">
        <h2 className="m-0 text-[15px] font-semibold">{title}</h2>
        <p className="m-0 text-[12.5px] text-fg-2">{body}</p>
        <span className="mt-1 inline-flex items-center gap-1.5 text-[11.5px] text-fg-3">
          <FlaskConical aria-hidden="true" className="h-3.5 w-3.5" />
          Ends in a backtest · no broker needed
        </span>
        <div className="mt-1.5">{action}</div>
      </div>
    </section>
  );
}

function TemplatePreview({ templates }: { templates: StrategyTemplate[] | null }) {
  if (templates === null) {
    return (
      <div className="grid gap-3" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </div>
    );
  }
  if (templates.length === 0) {
    return <p className="m-0 text-[12px] text-fg-3">Templates couldn&apos;t be loaded just now.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-1 p-0">
      {templates.slice(0, 4).map((t, i) => (
        <li key={t.id}>
          <Link
            to={`/welcome/template/${encodeURIComponent(t.id)}`}
            className={`flex items-center gap-2 rounded-[6px] px-2 py-1.5 text-[12.5px] transition-colors hover:bg-panel ${
              i === 0 ? 'bg-panel font-semibold text-fg' : 'text-fg-2'
            }`}
          >
            <span className="min-w-0 flex-1 truncate">{t.name}</span>
            <span className="num flex-none truncate text-[11px] font-normal text-fg-3">
              {templateMeta(t)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function CopilotPreview() {
  return (
    <div className="grid gap-2 text-[12px]">
      <span className="text-[11px] text-fg-3">For example</span>
      <div className="justify-self-end rounded-[10px] rounded-br-[3px] bg-panel px-3 py-2 text-fg">
        {EXAMPLE}
      </div>
      <div className="grid gap-1">
        <span className="text-[11px] font-medium text-fg-3">Copilot</span>
        <div className="rounded-[10px] rounded-bl-[3px] border border-line bg-canvas px-3 py-2 text-fg-2">
          Drafts the rules for you to read, then offers a backtest.
        </div>
      </div>
    </div>
  );
}

function BlocksPreview() {
  const box = 'rounded-[6px] border border-line bg-panel px-2.5 py-1.5 text-[11.5px]';
  return (
    <div className="grid gap-1.5" aria-label="An example strategy in blocks">
      <div className={box}>
        <span className="text-fg-3">If</span> <span className="num">10Y minus 2Y</span>{' '}
        <span className="text-fg-3">is below</span> <span className="num">0</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <div className={box}>
          <span className="block text-fg-3">Then hold</span>
          <span className="num">TLT 60% · GLD 40%</span>
        </div>
        <div className={box}>
          <span className="block text-fg-3">Otherwise</span>
          <span className="num">SPY 100%</span>
        </div>
      </div>
      <div className={box}>
        <span className="text-fg-3">Rebalance</span> <span className="num">daily</span>
      </div>
    </div>
  );
}

/** /welcome: three equal ways to a first strategy, each ending in a backtest (start2 A). */
export default function WelcomePage() {
  const navigate = useNavigate();
  const createNew = useStrategyBuilderStore((s) => s.createNew);
  const firstName = useAuthStore((s) => s.user?.firstName?.trim() ?? '');
  const credentials = useBrokerStore((s) => s.credentials);
  const fetchBroker = useBrokerStore((s) => s.fetch);
  const [templates, setTemplates] = useState<StrategyTemplate[] | null>(null);
  const [idea, setIdea] = useState('');

  useEffect(() => {
    fetchBroker().catch(() => undefined);
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
  }, [fetchBroker]);

  const paperConnected = credentials.some((c) => c.isPaper && c.isActive);
  const firstTemplate = templates?.[0]?.id ?? PREFERRED_TEMPLATE_ID;
  const count = templates?.length ?? 0;

  return (
    <OnboardingLayout step={1}>
      <StepTitle
        title={firstName ? `Welcome, ${firstName}` : 'Welcome to LlamaTrade'}
        lead="Make a first strategy and see how it would have done. Pick whichever way suits you."
      />
      <div className="grid w-full max-w-[1040px] gap-3.5 md:grid-cols-3">
        <Door
          title="Start from a template"
          body={`${count > 0 ? `${count} ready-made strategies` : 'Ready-made strategies'} with their rules written out. Run one as it is or change it first.`}
          preview={<TemplatePreview templates={templates} />}
          action={
            <Link
              to={`/welcome/template/${encodeURIComponent(firstTemplate)}`}
              className="btn btn-secondary btn-sm"
            >
              Choose a template
              <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
            </Link>
          }
        />
        <Door
          title="Describe it to Copilot"
          body="Say what you want in a sentence. Copilot drafts the rules, and you check them before anything runs."
          preview={<CopilotPreview />}
          action={
            <form
              className="grid gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                navigate(copilotUrl(idea));
              }}
            >
              <label htmlFor="idea" className="sr-only">
                Your strategy in a sentence
              </label>
              <textarea
                id="idea"
                rows={2}
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                className="input h-auto py-2 text-[12.5px]"
                placeholder="Your strategy in a sentence"
              />
              <button type="submit" className="btn btn-secondary btn-sm justify-self-start">
                Ask Copilot
                <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
              </button>
            </form>
          }
        />
        <Door
          title="Build from blocks"
          body="Put conditions, holdings and a schedule together yourself. Each block shows what it does as you add it."
          preview={<BlocksPreview />}
          action={
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                createNew();
                navigate('/strategies/builder');
              }}
            >
              Open the builder
              <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          }
        />
      </div>
      <AccountPath
        steps={startPath(paperConnected)}
        label="From a backtest to paper and live"
        className="w-full max-w-[1040px]"
      />
    </OnboardingLayout>
  );
}
