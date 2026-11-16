import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { useMemo } from 'react';

import { DIFFICULTY_LABELS } from '../../data/strategy-templates';
import { HOLDING_FILLS } from '../strategy-builder/outline/holdingFills';
import { StackedBar } from '../strategy-builder/rail/StackedBar';

import { holdingsShort, templateHoldings } from './templateModel';

interface TemplateCardProps {
  template: StrategyTemplate;
  onUse: (t: StrategyTemplate) => void;
  /** Full card with description, legend and a button; compact for the dialog grid. */
  variant?: 'full' | 'compact';
}

/** A template with its holdings drawn. */
export function TemplateCard({ template, onUse, variant = 'full' }: TemplateCardProps) {
  const holdings = useMemo(() => templateHoldings(template), [template]);
  const fixed = holdings.filter((h) => h.pct !== null);
  const bar = (
    <StackedBar
      label={`${template.name} holdings`}
      height={variant === 'full' ? 8 : 6}
      segments={(fixed.length
        ? fixed
        : holdings.map((h) => ({ ...h, pct: 100 / holdings.length }))
      ).map((h, i) => ({
        key: h.symbol,
        pct: h.pct ?? 0,
        fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
      }))}
    />
  );

  if (variant === 'compact') {
    return (
      <button
        type="button"
        onClick={() => onUse(template)}
        className="grid gap-2 rounded-panel border border-line bg-canvas p-3.5 text-left transition-colors hover:border-line-strong focus-visible:border-accent"
      >
        <b className="text-[13px] font-semibold">{template.name}</b>
        <span className="truncate text-[12px] text-fg-2">
          {holdingsShort(holdings) || template.description}
        </span>
        {bar}
      </button>
    );
  }

  return (
    <div className="grid content-start gap-3 rounded-panel border border-line bg-canvas p-4 text-left">
      <div className="flex items-center justify-between gap-2">
        <b className="text-[13.5px] font-semibold">{template.name}</b>
        <span className="inline-flex h-[21px] items-center rounded-full bg-sunk px-2 text-[11px] font-medium text-fg-2">
          {DIFFICULTY_LABELS[template.difficulty]}
        </span>
      </div>
      <p className="m-0 min-h-[38px] text-[12.5px] text-fg-2">{template.description}</p>
      {bar}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-fg-2">
        {holdings.slice(0, 6).map((h) => (
          <span key={h.symbol}>
            <b className="font-mono font-semibold text-fg">{h.symbol}</b>
            {h.pct !== null && ` ${Math.round(h.pct * 10) / 10}%`}
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onUse(template)}
        className="btn btn-secondary btn-sm justify-self-start"
      >
        Use this template
      </button>
    </div>
  );
}
