import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { FormNote } from '../../components/auth/fields';
import {
  outlineOf,
  rankTemplates,
  templateMeta,
  type TemplateOutline,
} from '../../components/home/templates';
import { EmptyState, PanelError, Skeleton, SkeletonRows, Tabs } from '../../components/ui';
import { CATEGORY_LABELS } from '../../data/strategy-templates';
import { formatMoney } from '../../lib/format';
import { listTemplates } from '../../services/strategy';

import { OnboardingLayout, StepTitle } from './OnboardingLayout';
import { FIRST_BACKTEST_CAPITAL, FIRST_BACKTEST_YEARS, startTemplateBacktest } from './runTemplate';

const DslCodeBlock = lazy(() => import('../../components/strategies/DslCodeBlock'));

const LIST_SIZE = 8;

type View = 'outline' | 'code';

function Outline({ outline }: { outline: TemplateOutline }) {
  if (outline.lines.length === 0) {
    return <p className="m-0 text-[12.5px] text-fg-3">This template has no outline to show.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-0 p-0 text-[13px]">
      {outline.lines.map((l, i) => (
        <li
          key={i}
          className="flex items-baseline justify-between gap-3 border-b border-line py-[7px] last:border-b-0"
          style={{ paddingLeft: l.depth * 16 }}
        >
          <span className={l.depth === 0 ? 'text-fg' : 'text-fg-2'}>{l.text}</span>
          {l.weight && <span className="num text-fg-2">{l.weight}</span>}
        </li>
      ))}
    </ul>
  );
}

function TemplateList({
  templates,
  selectedId,
}: {
  templates: StrategyTemplate[];
  selectedId: string;
}) {
  return (
    <nav
      aria-label="Templates"
      className="overflow-hidden rounded-panel border border-line bg-panel"
    >
      {templates.slice(0, LIST_SIZE).map((t) => {
        const on = t.id === selectedId;
        return (
          <Link
            key={t.id}
            to={`/welcome/template/${encodeURIComponent(t.id)}`}
            replace
            aria-current={on ? 'page' : undefined}
            className={`block border-b border-line px-3.5 py-2.5 text-[12.5px] last:border-b-0 ${
              on ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]' : 'hover:bg-sunk'
            }`}
          >
            <b className="block font-semibold text-fg">{t.name}</b>
            <span className="block text-[11.5px] text-fg-3">{templateMeta(t)}</span>
          </Link>
        );
      })}
      <Link
        to="/strategies/templates"
        className="block px-3.5 py-2.5 text-[12.5px] text-accent hover:underline"
      >
        All {templates.length} templates
      </Link>
    </nav>
  );
}

/** /welcome/template/:id: read a template, as an outline or as code, then backtest it. */
export default function WelcomeTemplatePage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<StrategyTemplate[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [view, setView] = useState<View>('outline');
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState('');

  const load = useCallback(() => {
    setLoadFailed(false);
    setTemplates(null);
    listTemplates()
      .then((r) => setTemplates(rankTemplates(r.templates)))
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(load, [load]);

  const template = templates?.find((t) => t.id === id) ?? null;
  const outline = useMemo(() => (template ? outlineOf(template.configSexpr) : null), [template]);
  const benchmark = outline?.benchmark ?? 'SPY';

  const run = async () => {
    if (!template) return;
    setRunning(true);
    setRunError('');
    try {
      const { runId } = await startTemplateBacktest(template, benchmark);
      navigate(`/welcome/result/${encodeURIComponent(runId)}`);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "The backtest couldn't be started.");
      setRunning(false);
    }
  };

  let body;
  if (loadFailed) {
    body = (
      <div className="w-full max-w-[960px] rounded-panel border border-line bg-panel">
        <PanelError
          title="Templates couldn't be loaded"
          cause="The strategy service didn't answer."
          onRetry={load}
        />
      </div>
    );
  } else if (!templates) {
    body = (
      <div
        className="grid w-full max-w-[960px] gap-4 md:grid-cols-[260px_minmax(0,1fr)]"
        aria-busy="true"
      >
        <div className="hidden rounded-panel border border-line bg-panel md:block">
          <SkeletonRows rows={6} cols={1} />
        </div>
        <div className="grid gap-3 rounded-panel border border-line bg-panel p-5">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
          <SkeletonRows rows={5} cols={2} />
        </div>
      </div>
    );
  } else if (!template) {
    body = (
      <div className="w-full max-w-[960px] rounded-panel border border-line bg-panel">
        <EmptyState
          title="That template isn't in the catalogue"
          body="It may have been renamed. Pick one from the list instead."
          actions={
            templates[0] && (
              <Link
                to={`/welcome/template/${encodeURIComponent(templates[0].id)}`}
                replace
                className="btn btn-primary"
              >
                Show {templates[0].name}
              </Link>
            )
          }
        />
      </div>
    );
  } else {
    body = (
      <div className="grid w-full max-w-[960px] gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
        <div className="hidden md:block">
          <TemplateList templates={templates} selectedId={template.id} />
        </div>
        <label className="grid gap-1.5 md:hidden">
          <span className="text-[12px] font-medium text-fg-2">Template</span>
          <select
            className="select"
            value={template.id}
            onChange={(e) =>
              navigate(`/welcome/template/${encodeURIComponent(e.target.value)}`, { replace: true })
            }
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <article className="grid min-w-0 content-start gap-3.5 rounded-panel border border-line bg-panel p-4 md:p-5">
          <header className="grid gap-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="m-0 text-[20px] font-semibold tracking-[-0.015em]">{template.name}</h2>
              <span className="badge uppercase tracking-[0.05em]">
                {CATEGORY_LABELS[template.category]}
              </span>
            </div>
            <p className="m-0 text-[13px] text-fg-2">{template.description}</p>
            <span className="text-[12px] text-fg-3">
              {[
                outline?.rebalance && `Rebalances ${outline.rebalance}`,
                `${outline?.symbols.length ?? 0} symbols`,
                `benchmark ${benchmark}`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </header>
          <Tabs<View>
            label="Template view"
            value={view}
            onChange={setView}
            options={[
              { key: 'outline', label: 'Outline' },
              { key: 'code', label: 'Code' },
            ]}
          />
          {view === 'outline' && outline ? (
            <Outline outline={outline} />
          ) : (
            <Suspense fallback={<SkeletonRows rows={6} cols={1} />}>
              <DslCodeBlock
                code={template.configSexpr}
                className="overflow-hidden rounded-panel border border-line"
              />
            </Suspense>
          )}
        </article>
      </div>
    );
  }

  return (
    <OnboardingLayout step={2}>
      <StepTitle
        title="Read a template"
        lead="This is the whole strategy. A backtest runs it over past prices, with no broker involved."
      />
      {body}
      {template && (
        <div className="grid w-full max-w-[960px] justify-items-center gap-2.5">
          {runError && (
            <div className="w-full max-w-[560px]">
              <FormNote tone="warn">{runError}</FormNote>
            </div>
          )}
          <div className="flex w-full flex-col-reverse gap-2.5 md:w-auto md:flex-row">
            <Link to="/welcome" className="btn btn-secondary btn-lg">
              Back
            </Link>
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={running}
              onClick={() => run().catch(() => undefined)}
            >
              {running ? 'Starting the backtest…' : 'Backtest this template'}
            </button>
          </div>
          <span className="text-center text-[12px] text-fg-3">
            Saves it to your strategies, then tests the last {FIRST_BACKTEST_YEARS} years with{' '}
            {formatMoney(FIRST_BACKTEST_CAPITAL, { dp: 0 })} of paper capital against {benchmark}.
          </span>
        </div>
      )}
    </OnboardingLayout>
  );
}
