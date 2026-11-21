import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import {
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  LayoutGrid,
  LineChart,
  Search,
  Shield,
  Wallet,
  type LucideIcon,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import {
  barShares,
  categoryCounts,
  goalTemplates,
  GOALS,
  holdingsShort,
  matchesTemplate,
  pickThree,
  templateHoldings,
  type CategoryCount,
  type GoalKey,
} from '../../components/strategies/templateModel';
import { TemplateActions, TemplatePreview } from '../../components/strategies/TemplatePreview';
import { useTemplates } from '../../components/strategies/useTemplates';
import { HOLDING_FILLS } from '../../components/strategy-builder/outline/holdingFills';
import { StackedBar } from '../../components/strategy-builder/rail/StackedBar';
import { NoMatch, PageHead, PanelError, Sheet, Skeleton, SkeletonRows } from '../../components/ui';
import { CATEGORY_LABELS, DIFFICULTY_LABELS } from '../../data/strategy-templates';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { rebalanceWord } from '../../lib/outline';

const GOAL_ICON: Record<GoalKey, LucideIcon> = {
  downturns: Shield,
  trends: LineChart,
  income: Wallet,
  growth: ArrowUpRight,
  fixed: LayoutGrid,
};

const catLabel = (c: CategoryCount['category']) => (c === 'all' ? 'All' : CATEGORY_LABELS[c]);
const isGoal = (v: string | null): v is GoalKey => GOALS.some((g) => g.key === v);

function rebalanceOf(t: StrategyTemplate): string {
  const w = rebalanceWord(fromDSLString(t.configSexpr)?.metadata.timeframe ?? '1D');
  return `${w[0].toUpperCase()}${w.slice(1)}`;
}

function FitCard({ template, onOpen }: { template: StrategyTemplate; onOpen: () => void }) {
  const holdings = useMemo(() => templateHoldings(template), [template]);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="panel grid content-start gap-3 px-5 py-4 text-left transition-colors hover:border-line-strong focus-visible:border-accent"
    >
      <span className="flex items-baseline justify-between gap-2 text-[12px] text-fg-3">
        <span>
          {CATEGORY_LABELS[template.category]} · {DIFFICULTY_LABELS[template.difficulty]}
        </span>
        <span>{rebalanceOf(template)}</span>
      </span>
      <b className="text-[17px] font-semibold tracking-[-0.01em]">{template.name}</b>
      <p className="m-0 line-clamp-4 min-h-[76px] text-[13px] text-fg-2">{template.description}</p>
      <span className="kicker mt-1">What it holds first</span>
      <StackedBar
        label={`${template.name} holdings`}
        height={8}
        segments={barShares(holdings).map((h, i) => ({
          key: h.symbol,
          pct: h.pct,
          fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
        }))}
      />
      <span className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[12px] text-fg-2">
        {holdings.slice(0, 6).map((h) => (
          <span key={h.symbol}>
            <b className="font-semibold text-fg">{h.symbol}</b>
            {h.pct !== null && ` ${Math.round(h.pct * 10) / 10}%`}
          </span>
        ))}
        {holdings.length > 6 && <span className="text-fg-3">+{holdings.length - 6}</span>}
      </span>
    </button>
  );
}

function TemplateRow({ template, onOpen }: { template: StrategyTemplate; onOpen: () => void }) {
  const short = useMemo(() => holdingsShort(templateHoldings(template)), [template]);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full gap-0.5 border-b border-line px-4 py-[11px] text-left last:border-b-0 hover:bg-sunk/60"
    >
      <span className="flex items-baseline justify-between gap-3">
        <b className="truncate text-[13.5px] font-semibold">{template.name}</b>
        <span className="flex-none text-[11.5px] text-fg-3">
          {CATEGORY_LABELS[template.category]} · {DIFFICULTY_LABELS[template.difficulty]}
        </span>
      </span>
      <span className="line-clamp-2 text-[12.5px] text-fg-2">{template.description || short}</span>
    </button>
  );
}

export default function TemplatesPage() {
  useDocumentTitle('Templates');
  const templates = useTemplates();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<CategoryCount['category']>('all');

  const all = useMemo(() => (templates.status === 'ready' ? templates.templates : []), [templates]);
  const goalParam = params.get('goal');
  const goal: GoalKey = isGoal(goalParam) ? goalParam : 'downturns';
  const browsing = params.get('view') === 'all';
  const goalFilter = browsing && isGoal(goalParam) ? goalParam : null;

  const byGoal = useMemo(
    () => Object.fromEntries(GOALS.map((g) => [g.key, goalTemplates(all, g.key)])),
    [all]
  ) as Record<GoalKey, StrategyTemplate[]>;
  const three = useMemo(() => pickThree(byGoal[goal] ?? []), [byGoal, goal]);

  const browseBase = goalFilter ? byGoal[goalFilter] : all;
  const counts = useMemo(() => categoryCounts(browseBase), [browseBase]);
  const shown = useMemo(
    () =>
      browseBase.filter(
        (t) => (category === 'all' || t.category === category) && matchesTemplate(t, query)
      ),
    [browseBase, category, query]
  );

  const update = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(params);
      for (const [k, v] of Object.entries(patch)) {
        if (v === null) next.delete(k);
        else next.set(k, v);
      }
      setParams(next, { replace: true });
    },
    [params, setParams]
  );

  const list = browsing ? shown : three;
  const openId = params.get('t');
  const openIdx = list.findIndex((t) => t.id === openId);
  const open = openIdx >= 0 ? list[openIdx] : all.find((t) => t.id === openId);
  const step = useCallback(
    (d: number) => {
      if (openIdx < 0 || !list.length) return;
      update({ t: list[(openIdx + d + list.length) % list.length].id });
    },
    [openIdx, list, update]
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') step(1);
      if (e.key === 'ArrowUp') step(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, step]);

  const total = templates.status === 'ready' ? all.length : null;
  const goalCount = byGoal[goal]?.length ?? 0;

  const crumbs = [{ label: 'Strategies', to: '/strategies' }, { label: 'Templates' }];

  return (
    <div className="page relative isolate">
      {browsing ? (
        <PageHead
          crumbs={crumbs}
          title={
            goalFilter ? (GOALS.find((g) => g.key === goalFilter)?.title ?? '') : 'All templates'
          }
          documentTitle="Templates"
          sub={
            total === null
              ? 'Strategies to start from.'
              : `${browseBase.length} of ${total} templates. Open one to see what it holds and its rules.`
          }
          actions={
            <button
              type="button"
              onClick={() => update({ view: null })}
              className="btn btn-secondary"
            >
              Start from a goal
            </button>
          }
        />
      ) : (
        <div className="mb-6 grid justify-items-center gap-2 text-center">
          <nav aria-label="Breadcrumb" className="text-[12.5px] text-fg-3">
            <Link to="/strategies" className="hover:text-fg">
              Strategies
            </Link>
            <span className="mx-1.5">›</span>
            <span className="text-fg-2">Templates</span>
          </nav>
          <h1 className="m-0 text-[30px] font-semibold tracking-[-0.03em] md:text-[38px]">
            What should this money do?
          </h1>
          <p className="m-0 max-w-[620px] text-[15px] text-fg-2">
            Choose the closest goal to see three of the {total ?? ''} templates that fit it. You can
            change any rule after you pick one.
          </p>
        </div>
      )}

      {templates.status === 'error' ? (
        <div className="panel">
          <PanelError
            title="Templates couldn’t be loaded"
            cause="The strategy service didn’t answer."
            unaffected="Your strategies aren’t affected."
            onRetry={templates.retry}
          />
        </div>
      ) : browsing ? (
        <div className="grid items-start gap-4 lg:grid-cols-[190px_minmax(0,1fr)]">
          <div className="grid gap-1">
            <label className="mb-2.5 flex h-9 items-center gap-2 rounded-[6px] border border-line-strong bg-panel px-3 focus-within:border-accent">
              <Search className="h-4 w-4 text-fg-3" aria-hidden="true" />
              <span className="sr-only">Search templates</span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search templates"
                className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-fg-3"
              />
            </label>
            <span className="kicker mx-2 mb-1 hidden lg:block">Approach</span>
            <div
              role="radiogroup"
              aria-label="Approach"
              className="no-scrollbar flex gap-1.5 overflow-x-auto lg:grid lg:gap-0.5"
            >
              {templates.status === 'loading'
                ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-6 w-24" />)
                : counts.map((c) => {
                    const on = c.category === category;
                    return (
                      <button
                        key={c.category}
                        type="button"
                        role="radio"
                        aria-checked={on}
                        onClick={() => setCategory(c.category)}
                        className={`flex-none whitespace-nowrap rounded-full px-3 py-1 text-left text-[12.5px] lg:rounded-r lg:px-2 lg:py-[5px] ${
                          on
                            ? 'bg-accent-soft text-accent lg:bg-sunk lg:text-fg'
                            : 'text-fg-2 shadow-[inset_0_0_0_1px_rgb(var(--line-strong))] hover:text-fg lg:shadow-none'
                        }`}
                      >
                        {catLabel(c.category)} · {c.count}
                      </button>
                    );
                  })}
            </div>
          </div>
          <div className="panel overflow-hidden">
            {templates.status === 'loading' ? (
              <SkeletonRows rows={8} cols={1} />
            ) : shown.length === 0 ? (
              <NoMatch
                noun="templates"
                query={query}
                filters={category === 'all' ? [] : [catLabel(category)]}
                total={browseBase.length}
                onClear={() => {
                  setQuery('');
                  setCategory('all');
                }}
              />
            ) : (
              shown.map((t) => (
                <TemplateRow key={t.id} template={t} onOpen={() => update({ t: t.id })} />
              ))
            )}
          </div>
        </div>
      ) : (
        <>
          <div
            role="radiogroup"
            aria-label="Goal"
            className="mx-auto grid max-w-[1200px] grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5"
          >
            {GOALS.map((g) => {
              const on = g.key === goal;
              const Icon = GOAL_ICON[g.key];
              return (
                <button
                  key={g.key}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => update({ goal: g.key, t: null })}
                  className={`grid content-start gap-1.5 rounded-panel px-4 py-4 text-left transition-colors ${
                    on
                      ? 'panel-rim bg-accent-soft'
                      : 'border border-line bg-panel hover:border-line-strong'
                  }`}
                >
                  <span
                    className={`mb-2 grid h-7 w-7 place-items-center rounded-[6px] ${
                      on ? 'bg-accent text-canvas' : 'border border-line bg-sunk text-fg-2'
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <b className="text-[14px] font-semibold">{g.title}</b>
                  <span className="text-[12.5px] text-fg-2">{g.body}</span>
                  <span
                    className={`mt-1.5 font-mono text-[11.5px] ${on ? 'text-accent' : 'text-fg-3'}`}
                  >
                    {templates.status === 'ready' ? `${byGoal[g.key].length} templates` : ' '}
                  </span>
                </button>
              );
            })}
          </div>

          <section className="mx-auto mt-8 max-w-[1200px]" aria-label="Templates that fit">
            <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <b className="text-[15px] font-semibold">
                {goalCount > 3 ? `Three that fit, of ${goalCount}` : 'The templates that fit'}
              </b>
              <span className="text-[12.5px] text-fg-3">
                Simplest first, one from each approach
              </span>
            </div>
            <div className="grid gap-3.5 md:grid-cols-3">
              {templates.status === 'loading'
                ? [0, 1, 2].map((i) => (
                    <div key={i} className="panel grid gap-3 p-5" aria-hidden="true">
                      <Skeleton className="h-3 w-24" />
                      <Skeleton className="h-4 w-40" />
                      <Skeleton className="h-16 w-full" />
                      <Skeleton className="h-2 w-full" />
                    </div>
                  ))
                : three.map((t) => (
                    <FitCard key={t.id} template={t} onOpen={() => update({ t: t.id })} />
                  ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="m-0 max-w-[640px] text-[12px] text-fg-3">
                Templates don’t come with a backtest yet, so these aren’t ranked by results. Use one
                and backtest it over your own dates before anything runs.
              </p>
              <span className="flex gap-2">
                {goalCount > 3 && (
                  <button
                    type="button"
                    onClick={() => update({ view: 'all', goal })}
                    className="btn btn-secondary"
                  >
                    See all {goalCount}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => update({ view: 'all', goal: null })}
                  className="btn btn-ghost"
                >
                  {total ? `Browse all ${total}` : 'Browse all'}
                </button>
              </span>
            </div>
          </section>
        </>
      )}

      <Sheet
        open={open !== undefined}
        onClose={() => update({ t: null })}
        width={620}
        title={
          <span className="flex items-center gap-1">
            Template
            {openIdx >= 0 && list.length > 1 && (
              <span className="ml-2 flex gap-0.5">
                <button
                  type="button"
                  onClick={() => step(-1)}
                  aria-label="Previous template"
                  className="btn btn-ghost btn-sm px-1.5"
                >
                  <ChevronUp className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => step(1)}
                  aria-label="Next template"
                  className="btn btn-ghost btn-sm px-1.5"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
              </span>
            )}
          </span>
        }
        footer={open ? <TemplateActions template={open} /> : undefined}
      >
        <div className="px-6 py-5">{open && <TemplatePreview key={open.id} template={open} />}</div>
      </Sheet>
    </div>
  );
}
