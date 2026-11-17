import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { useMemo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useUIStore } from '../../store/ui';
import { HOLDING_FILLS } from '../strategy-builder/outline/holdingFills';
import { StackedBar } from '../strategy-builder/rail/StackedBar';
import { Skeleton } from '../ui';

import { barShares, pickStarters, templateHoldings } from './templateModel';
import { useStartDraft } from './useStartDraft';
import { useTemplates } from './useTemplates';

function Card({
  art,
  title,
  body,
  action,
  featured,
}: {
  art: ReactNode;
  title: string;
  body: string;
  action: ReactNode;
  featured?: boolean;
}) {
  return (
    <div
      className={`grid grid-rows-[auto_1fr] overflow-hidden rounded-panel bg-panel ${
        featured ? 'panel-rim' : 'border border-line'
      }`}
    >
      <div className="flex min-h-[132px] flex-col justify-center gap-2 border-b border-line bg-sunk/60 px-4 py-4">
        {art}
      </div>
      <div className="grid content-start gap-2 px-5 pb-5 pt-4">
        <b className="text-[15px] font-semibold">{title}</b>
        <p className="m-0 text-[13px] text-fg-2">{body}</p>
        <div className="mt-1.5">{action}</div>
      </div>
    </div>
  );
}

function TemplateArt({ template }: { template: StrategyTemplate | undefined }) {
  const holdings = useMemo(() => (template ? templateHoldings(template) : []), [template]);
  if (!template) return <Skeleton className="h-16 w-full" />;
  return (
    <div className="grid gap-2.5 rounded-[8px] border border-line bg-panel px-3.5 py-3 shadow-sm">
      <b className="text-[13px] font-semibold">{template.name}</b>
      <StackedBar
        label={`${template.name} holdings`}
        height={8}
        segments={barShares(holdings).map((h, i) => ({
          key: h.symbol,
          pct: h.pct,
          fill: HOLDING_FILLS[i % HOLDING_FILLS.length],
        }))}
      />
      <span className="flex flex-wrap gap-x-2.5 font-mono text-[11px] text-fg-2">
        {holdings.slice(0, 4).map((h) => (
          <span key={h.symbol}>
            {h.symbol}
            {h.pct !== null && ` ${Math.round(h.pct)}%`}
          </span>
        ))}
      </span>
    </div>
  );
}

const Token = ({ children, kw }: { children: ReactNode; kw?: boolean }) => (
  <span
    className={`inline-flex h-[24px] w-fit items-center rounded-[5px] border border-line-strong bg-panel px-2 font-mono text-[11px] ${
      kw ? 'font-semibold text-accent' : 'text-fg-2'
    }`}
  >
    {children}
  </span>
);

/**
 * The three ways into a first strategy (empty2 A): a template, a sentence for Copilot, or
 * blocks. The pictures show what each path looks like; they are examples, not your data.
 */
export function ThreeWays() {
  const templates = useTemplates();
  const { blank } = useStartDraft();
  const openNew = useUIStore((s) => s.openNewStrategyDialog);
  const starter = templates.status === 'ready' ? pickStarters(templates.templates)[0] : undefined;
  const count = templates.status === 'ready' ? templates.templates.length : null;

  return (
    <div className="grid gap-3.5 md:grid-cols-3">
      <Card
        featured
        art={<TemplateArt template={starter} />}
        title="Start from a template"
        body={`${count ? `${count} strategies` : 'Strategies'} to start from. Change any rule before it runs.`}
        action={
          <Link to="/strategies/templates" className="btn btn-primary btn-sm">
            Browse templates
          </Link>
        }
      />
      <Card
        art={
          <>
            <span className="ml-auto max-w-[88%] rounded-[8px] bg-fg px-3 py-2 text-[12px] text-canvas">
              Hold bonds and gold when SPY falls below its 200-day average
            </span>
            <span className="max-w-[88%] rounded-[8px] border border-line bg-panel px-3 py-2 text-[12px] text-fg-2">
              Here’s a draft with three rules. It checks SPY daily and rebalances monthly.
            </span>
          </>
        }
        title="Describe it to Copilot"
        body="Write the idea in a sentence. Copilot drafts the rules and explains each one."
        action={
          <button type="button" onClick={openNew} className="btn btn-secondary btn-sm">
            Describe a strategy
          </button>
        }
      />
      <Card
        art={
          <div className="grid gap-1.5">
            <Token kw>if SPY above 200-day average</Token>
            <span className="ml-5">
              <Token>hold VTI 60% · BND 40%</Token>
            </span>
            <Token kw>else</Token>
            <span className="ml-5">
              <Token>hold TLT 50% · GLD 50%</Token>
            </span>
          </div>
        }
        title="Build from blocks"
        body="Set conditions, weights and a rebalance schedule yourself."
        action={
          <button type="button" onClick={() => blank('tree')} className="btn btn-secondary btn-sm">
            Open the builder
          </button>
        }
      />
    </div>
  );
}
