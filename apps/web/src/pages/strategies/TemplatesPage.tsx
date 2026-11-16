import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { ArrowLeft, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import {
  categoryCounts,
  holdingsShort,
  matchesTemplate,
  templateHoldings,
  type CategoryCount,
} from '../../components/strategies/templateModel';
import { TemplatePreview } from '../../components/strategies/TemplatePreview';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { useTemplates } from '../../components/strategies/useTemplates';
import { NoMatch, PanelError, Sheet, Skeleton, SkeletonRows } from '../../components/ui';
import { CATEGORY_LABELS, DIFFICULTY_LABELS } from '../../data/strategy-templates';

const catLabel = (c: CategoryCount['category']) => (c === 'all' ? 'All' : CATEGORY_LABELS[c]);

function TemplateRow({
  template,
  selected,
  onSelect,
}: {
  template: StrategyTemplate;
  selected: boolean;
  onSelect: () => void;
}) {
  const short = useMemo(() => holdingsShort(templateHoldings(template)), [template]);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={`grid w-full gap-0.5 border-b border-line px-4 py-[11px] text-left last:border-b-0 ${
        selected ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]' : 'hover:bg-sunk/60'
      }`}
    >
      <span className="flex items-baseline justify-between gap-3">
        <b className="truncate text-[14px] font-semibold lg:text-[13px]">{template.name}</b>
        <span className="flex-none text-[11px] text-fg-3">
          {DIFFICULTY_LABELS[template.difficulty]}
        </span>
      </span>
      <span className="line-clamp-2 text-[12.5px] text-fg-2 lg:text-[12px]">
        {template.description || short}
      </span>
    </button>
  );
}

export default function TemplatesPage() {
  const templates = useTemplates();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<CategoryCount['category']>('all');
  const wide = useMediaQuery('(min-width: 1024px)');

  const all = useMemo(() => (templates.status === 'ready' ? templates.templates : []), [templates]);
  const counts = useMemo(() => categoryCounts(all), [all]);
  const shown = useMemo(
    () =>
      all.filter(
        (t) => (category === 'all' || t.category === category) && matchesTemplate(t, query)
      ),
    [all, category, query]
  );
  const selectedId = params.get('t');
  const selected = shown.find((t) => t.id === selectedId) ?? (wide ? shown[0] : undefined);
  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('t', id);
    else next.delete('t');
    setParams(next, { replace: true });
  };
  const clear = () => {
    setQuery('');
    setCategory('all');
  };

  const total = templates.status === 'ready' ? all.length : null;

  return (
    <div className="page">
      <Link
        to="/strategies"
        className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Strategies
      </Link>
      <h1 className="m-0 mt-1 text-[22px] font-semibold tracking-[-0.015em]">Templates</h1>
      <p className="m-0 mt-1 text-[13px] text-fg-2">
        {total === null ? 'Strategies to start from.' : `${total} strategies to start from.`}{' '}
        Preview one, then use it as is or customise it.
      </p>

      {templates.status === 'error' ? (
        <div className="panel mt-5">
          <PanelError
            title="Templates couldn’t be loaded"
            cause="The strategy service didn’t answer."
            unaffected="Your strategies aren’t affected."
            onRetry={templates.retry}
          />
        </div>
      ) : (
        <div className="mt-5 grid items-start gap-4 lg:grid-cols-[170px_340px_minmax(0,1fr)]">
          <div className="grid gap-1">
            <label className="mb-2.5 flex h-9 items-center gap-2 rounded-[6px] border border-line-strong bg-panel px-3 focus-within:border-accent">
              <Search className="h-4 w-4 text-fg-3" aria-hidden="true" />
              <span className="sr-only">Search templates</span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={total ? `Search ${total} templates` : 'Search'}
                className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-fg-3"
              />
            </label>
            <span className="kicker mx-2 mb-1 hidden lg:block">Category</span>
            <div
              role="radiogroup"
              aria-label="Category"
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

          <div className="panel overflow-hidden lg:max-h-[calc(100vh-176px)] lg:overflow-y-auto">
            {templates.status === 'loading' ? (
              <SkeletonRows rows={8} cols={1} />
            ) : shown.length === 0 ? (
              <NoMatch
                noun="templates"
                query={query}
                filters={category === 'all' ? [] : [catLabel(category)]}
                total={all.length}
                onClear={clear}
              />
            ) : (
              shown.map((t) => (
                <TemplateRow
                  key={t.id}
                  template={t}
                  selected={selected?.id === t.id}
                  onSelect={() => select(t.id)}
                />
              ))
            )}
          </div>

          {wide && (
            <div className="panel px-5 py-[18px] lg:sticky lg:top-[72px]">
              {selected ? (
                <TemplatePreview key={selected.id} template={selected} />
              ) : (
                <p className="m-0 text-[13px] text-fg-3">Pick a template to preview it.</p>
              )}
            </div>
          )}
        </div>
      )}

      {!wide && (
        <Sheet open={selected !== undefined} onClose={() => select(null)} title="Template">
          <div className="p-4">{selected && <TemplatePreview template={selected} />}</div>
        </Sheet>
      )}
    </div>
  );
}
