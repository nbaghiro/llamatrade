import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { ChevronRight, Blocks, Sparkles } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { CATEGORY_LABELS } from '../../data/strategy-templates';
import { copilotUrl } from '../../lib/palette';
import { listTemplates } from '../../services/strategy';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import { Skeleton } from '../ui';

import { outlineOf, PREFERRED_TEMPLATE_ID, rankTemplates } from './templates';

/** The first two templates, or null while loading and [] when the catalogue couldn't be read. */
function useStarterTemplates(): { list: StrategyTemplate[] | null; total: number } {
  const [list, setList] = useState<StrategyTemplate[] | null>(null);
  useEffect(() => {
    let live = true;
    listTemplates()
      .then((r) => live && setList(rankTemplates(r.templates)))
      .catch(() => live && setList([]));
    return () => {
      live = false;
    };
  }, []);
  return { list, total: list?.length ?? 0 };
}

function Card({
  rim,
  art,
  title,
  body,
  action,
  artOnPhone = false,
}: {
  rim?: boolean;
  art: ReactNode;
  title: string;
  body: string;
  action: ReactNode;
  artOnPhone?: boolean;
}) {
  return (
    <section
      aria-label={title}
      className={`flex flex-col overflow-hidden ${rim ? 'panel-rim' : 'rounded-panel border border-line bg-panel'}`}
    >
      <div
        className={`relative h-[200px] overflow-hidden border-b border-line bg-sunk px-6 py-6 md:block md:h-[230px] ${artOnPhone ? 'block' : 'hidden'}`}
      >
        {art}
      </div>
      <div className="flex flex-1 flex-col gap-2.5 px-6 pb-6 pt-5">
        <h2 className="m-0 text-[17px] font-semibold tracking-[-0.01em]">{title}</h2>
        <p className="m-0 text-[13.5px] leading-relaxed text-fg-2">{body}</p>
        <div className="mt-auto pt-2">{action}</div>
      </div>
    </section>
  );
}

function TemplateArt({ list }: { list: StrategyTemplate[] | null }) {
  if (list === null) return <Skeleton className="h-[140px] w-full" />;
  const [first, second] = list;
  if (!first) {
    return (
      <div className="grid h-full place-content-center text-[13px] text-fg-3">
        Templates couldn&apos;t be loaded just now.
      </div>
    );
  }
  const lines = outlineOf(first.configSexpr).lines.slice(0, 4);
  return (
    <>
      {second && (
        <div className="absolute left-10 right-3 top-3 rounded-[8px] border border-line bg-panel px-4 py-2.5 opacity-70">
          <div className="flex items-center justify-between text-[12.5px] font-semibold">
            {second.name}
            <span className="badge">{CATEGORY_LABELS[second.category]}</span>
          </div>
        </div>
      )}
      <div className="relative mt-6 rounded-[8px] border border-line bg-panel px-4 py-3 shadow-md">
        <div className="flex items-center justify-between gap-2 text-[13px] font-semibold">
          <span className="truncate">{first.name}</span>
          <span className="badge flex-none">{CATEGORY_LABELS[first.category]}</span>
        </div>
        <ul className="m-0 mt-2.5 grid list-none gap-1 p-0 font-mono text-[11.5px] text-fg-2">
          {lines.map((l, i) => (
            <li
              key={i}
              className="flex justify-between gap-2"
              style={{ paddingLeft: l.depth * 12 }}
            >
              <span className="truncate">{l.text}</span>
              {l.weight && <span className="text-fg">{l.weight}</span>}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

function CopilotArt() {
  return (
    <div className="grid gap-3 text-[12.5px] leading-snug">
      <div className="ml-auto max-w-[85%] rounded-[10px] bg-fg px-3.5 py-2.5 text-canvas">
        Hold bonds and gold when SPY falls below its 200-day average
      </div>
      <div className="max-w-[85%] rounded-[10px] border border-line bg-panel px-3.5 py-2.5 text-fg-2">
        Here&apos;s a draft with three rules. It checks SPY daily and rebalances monthly. Want me to
        run a backtest?
      </div>
    </div>
  );
}

function BlocksArt() {
  const blocks: [string, string, number][] = [
    ['if', 'SPY above 200-day average', 0],
    ['hold', 'VTI 60% · BND 40%', 1],
    ['else', '', 0],
    ['hold', 'TLT 50% · GLD 50%', 1],
  ];
  return (
    <div className="grid gap-2.5 font-mono text-[12px]">
      {blocks.map(([k, text, depth], i) => (
        <div
          key={i}
          className="rounded-[6px] border border-line bg-panel px-3 py-2"
          style={{ marginLeft: depth * 22 }}
        >
          <span className="mr-2 text-accent">{k}</span>
          <span className="text-fg">{text}</span>
        </div>
      ))}
    </div>
  );
}

/** home/first-visit2 B: three ways to make a first strategy, each showing what that path looks like. */
export function FirstVisit({ hasStrategies }: { hasStrategies: boolean }) {
  const { list, total } = useStarterTemplates();
  const navigate = useNavigate();
  const createNew = useStrategyBuilderStore((s) => s.createNew);
  const openBuilder = () => {
    createNew();
    navigate('/strategies/builder');
  };
  const first = list?.[0]?.id ?? PREFERRED_TEMPLATE_ID;
  const pill = 'btn rounded-full px-4';

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3 md:gap-5">
      <Card
        rim
        artOnPhone
        art={<TemplateArt list={list} />}
        title="Start from a template"
        body={`${total ? `${total} strategies` : 'Ready-made strategies'}, from a classic 60/40 to sector rotation. Preview one, change any rule and backtest it before it runs.`}
        action={
          <div className="flex flex-wrap items-center gap-3">
            <Link to="/strategies/templates" className={`${pill} btn-primary`}>
              Browse templates
            </Link>
            {list && list.length > 0 && (
              <Link
                to={`/welcome/template/${encodeURIComponent(first)}`}
                className="inline-flex items-center gap-0.5 text-[13px] text-accent hover:underline"
              >
                Preview {list[0].name}
                <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
        }
      />
      <Card
        art={<CopilotArt />}
        title="Describe it to Copilot"
        body="Write the idea in a sentence. Copilot drafts the rules and explains each one, and you edit the result."
        action={
          <Link to={copilotUrl('')} className={`${pill} btn-secondary`}>
            <Sparkles aria-hidden="true" className="h-4 w-4" />
            Describe a strategy
          </Link>
        }
      />
      <Card
        art={<BlocksArt />}
        title="Build from blocks"
        body={
          hasStrategies
            ? 'Open the builder to change one of your strategies or assemble a new one from conditions, weights and a schedule.'
            : 'Assemble conditions, weights and a rebalance schedule yourself. Best if you already know the rules you want.'
        }
        action={
          <button type="button" onClick={openBuilder} className={`${pill} btn-secondary`}>
            <Blocks aria-hidden="true" className="h-4 w-4" />
            Open the builder
          </button>
        }
      />
    </div>
  );
}
