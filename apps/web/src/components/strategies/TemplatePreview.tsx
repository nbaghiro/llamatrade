import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { Info, Sparkles } from 'lucide-react';
import { lazy, Suspense, useMemo, useState } from 'react';

import { CATEGORY_LABELS, DIFFICULTY_LABELS } from '../../data/strategy-templates';
import { buildOutline, metaParts, rebalanceWord, strategySymbols } from '../../lib/outline';
import { Outline, Parts } from '../strategy-builder/outline/Outline';
import { Segmented, Skeleton } from '../ui';

import { useStartDraft } from './useStartDraft';

const DslCodeBlock = lazy(() => import('./DslCodeBlock'));

const VIEWS = [
  { key: 'outline', label: 'Outline' },
  { key: 'code', label: 'Code' },
] as const;

/** A template as an outline, with its code one tab away. */
export function TemplatePreview({ template }: { template: StrategyTemplate }) {
  const [view, setView] = useState<'outline' | 'code'>('outline');
  const { fromTemplate } = useStartDraft();
  const openSeededChat = useAgentStore((s) => s.openSeededChat);
  const openPanel = useAgentStore((s) => s.openPanel);
  const parsed = useMemo(() => fromDSLString(template.configSexpr), [template.configSexpr]);
  const lines = useMemo(() => (parsed ? buildOutline(parsed.tree) : []), [parsed]);
  const timeframe = parsed?.metadata.timeframe ?? '1D';
  const symbols = parsed ? strategySymbols(parsed.tree).held.length : 0;

  const customise = () => {
    fromTemplate(template);
    openSeededChat(`Help me customise the “${template.name}” template.`);
    openPanel();
  };

  return (
    <div className="grid gap-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <b className="text-[17px] font-semibold">{template.name}</b>
          <p className="m-0 mt-0.5 text-[12px] text-fg-3">
            {[
              CATEGORY_LABELS[template.category],
              DIFFICULTY_LABELS[template.difficulty],
              `${symbols} ${symbols === 1 ? 'symbol' : 'symbols'}`,
              rebalanceWord(timeframe),
            ].join(' · ')}
          </p>
        </div>
        <div className="flex gap-1.5">
          <button type="button" onClick={customise} className="btn btn-secondary">
            <Sparkles className="h-4 w-4" />
            Customise
          </button>
          <button type="button" onClick={() => fromTemplate(template)} className="btn btn-primary">
            Use this template
          </button>
        </div>
      </div>
      {template.description && <p className="m-0 text-[13px] text-fg-2">{template.description}</p>}
      <Segmented
        label="Template view"
        options={VIEWS}
        value={view}
        onChange={setView}
        className="justify-self-start"
      />
      {view === 'outline' ? (
        parsed ? (
          <div>
            <p className="m-0 mb-3 text-[13px] text-fg-2">
              <Parts parts={metaParts({ timeframe, benchmark: parsed.metadata.benchmark ?? '' })} />
            </p>
            <Outline lines={lines} dense label={`${template.name} outline`} />
          </div>
        ) : (
          <p className="m-0 text-[13px] text-fg-2">
            This template can’t be shown as an outline. Its code is one tab away.
          </p>
        )
      ) : (
        <Suspense fallback={<Skeleton className="h-40 w-full" />}>
          <DslCodeBlock code={template.configSexpr} className="rounded-panel border border-line" />
        </Suspense>
      )}
      <div className="grid grid-cols-[16px_minmax(0,1fr)] items-start gap-2.5 rounded-panel border border-line bg-panel px-3.5 py-2.5 text-[12.5px] text-fg-2">
        <Info className="mt-0.5 h-4 w-4 text-fg-3" aria-hidden="true" />
        No track record yet. Backtest it after creating to see how it would have done.
      </div>
    </div>
  );
}
