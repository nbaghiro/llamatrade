import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { Info } from 'lucide-react';
import { lazy, Suspense, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { CATEGORY_LABELS, DIFFICULTY_LABELS } from '../../data/strategy-templates';
import { buildOutline, metaParts, rebalanceWord } from '../../lib/outline';
import { askCopilotHref } from '../agent/entry';
import { CopilotMark } from '../common/Logo';
import { HOLDING_FILLS } from '../strategy-builder/outline/holdingFills';
import { Outline, Parts } from '../strategy-builder/outline/Outline';
import { StackedBar } from '../strategy-builder/rail/StackedBar';
import { Segmented, Skeleton } from '../ui';

import { holdingWords, holdSentences } from './holdSentences';
import { codeFragments } from './rules/codeFragments';
import { ruleSentence, type SentenceTerm } from './rules/ruleSentence';
import { RuleSentenceView } from './rules/RuleSentenceView';
import { barShares } from './templateModel';
import { useStartDraft } from './useStartDraft';

const DslCodeBlock = lazy(() => import('./DslCodeBlock'));

const VIEWS = [
  { key: 'outline', label: 'Outline' },
  { key: 'code', label: 'Code' },
] as const;

const Chip = ({ children }: { children: string }) => (
  <span className="inline-flex h-[22px] items-center rounded-full border border-line-strong px-2.5 text-[11.5px] text-fg-2">
    {children}
  </span>
);

/** Customise with Copilot, or use the template as is. */
export function TemplateActions({ template }: { template: StrategyTemplate }) {
  const { fromTemplate } = useStartDraft();
  const navigate = useNavigate();
  const customise = () => {
    navigate(askCopilotHref(`Help me customise the “${template.name}” template.`));
  };
  return (
    <>
      <button type="button" onClick={customise} className="btn btn-secondary">
        <CopilotMark className="h-4 w-4" />
        Customise
      </button>
      <button type="button" onClick={() => fromTemplate(template)} className="btn btn-primary">
        Use this template
      </button>
    </>
  );
}

/** What one underlined part of a template's sentence is in its code. */
function TermNote({
  term,
  fragments,
}: {
  term: SentenceTerm;
  fragments: ReadonlyMap<string, string>;
}) {
  const t = term.target;
  const code =
    t.kind === 'rebalance' ? null : t.kind === 'fold' ? null : (fragments.get(t.blockId) ?? null);
  return (
    <div className="grid gap-1.5 rounded-panel border border-line bg-sunk/60 px-3.5 py-2.5 text-[12.5px] text-fg-2">
      {t.kind === 'fold' ? (
        t.of === 'symbols' ? (
          <span className="font-mono text-fg">{t.rules.map((r) => r.text).join(' ')}</span>
        ) : (
          t.rules.map((r) => (
            <span key={r.number}>
              <span className="mr-2 font-mono text-fg-3">{r.number}</span>
              {r.text}
            </span>
          ))
        )
      ) : t.kind === 'rebalance' ? (
        <span>
          The rules are checked on the first daily bar of each period, and orders go in then.
        </span>
      ) : (
        <>
          {'rule' in t && t.rule ? <span>Rule {t.rule} in the outline below.</span> : null}
          {code && <code className="font-mono text-[12px] text-fg">{code}</code>}
        </>
      )}
    </div>
  );
}

/**
 * A template in the side drawer (template-preview A): what it holds on each side of its rules,
 * the rules as an outline, and the code one tab away.
 */
export function TemplatePreview({
  template,
  showActions = false,
}: {
  template: StrategyTemplate;
  showActions?: boolean;
}) {
  const [view, setView] = useState<'outline' | 'code'>('outline');
  const parsed = useMemo(() => fromDSLString(template.configSexpr), [template.configSexpr]);
  const lines = useMemo(() => (parsed ? buildOutline(parsed.tree) : []), [parsed]);
  const sentences = useMemo(() => (parsed ? holdSentences(parsed.tree) : []), [parsed]);
  const timeframe = parsed?.metadata.timeframe ?? '1D';
  const rebalance = rebalanceWord(timeframe);
  const sentence = useMemo(
    () => (parsed ? ruleSentence(parsed.tree, timeframe) : null),
    [parsed, timeframe]
  );
  const fragments = useMemo(
    () => (parsed ? codeFragments(template.configSexpr, parsed.tree) : new Map<string, string>()),
    [parsed, template.configSexpr]
  );
  const [openId, setOpenId] = useState<string | null>(null);
  const open = sentence?.parts.find((p): p is SentenceTerm => p.kind === 'term' && p.id === openId);

  return (
    <div className="grid gap-5">
      <div className="grid gap-2">
        <div className="flex flex-wrap gap-1.5">
          <Chip>{CATEGORY_LABELS[template.category]}</Chip>
          <Chip>{DIFFICULTY_LABELS[template.difficulty]}</Chip>
          <Chip>{`${rebalance[0].toUpperCase()}${rebalance.slice(1)}`}</Chip>
        </div>
        <h2 className="m-0 text-[24px] font-semibold tracking-[-0.02em]">{template.name}</h2>
        {template.description && (
          <p className="m-0 text-[13.5px] text-fg-2">{template.description}</p>
        )}
        {sentence && (
          <div className="mt-1 grid gap-2">
            <RuleSentenceView
              parts={sentence.parts}
              openId={openId}
              onOpen={(id) => setOpenId((cur) => (cur === id ? null : id))}
              className="text-[17px] leading-[1.6] text-fg-2"
            />
            {open && <TermNote term={open} fragments={fragments} />}
          </div>
        )}
        {showActions && (
          <div className="mt-1 flex flex-wrap gap-2">
            <TemplateActions template={template} />
          </div>
        )}
      </div>

      {sentences.length > 0 && (
        <section className="grid gap-3 border-t border-line pt-4">
          <span className="kicker">What it holds</span>
          {sentences.slice(0, 4).map((s, i) => {
            return (
              <div key={i} className="grid gap-1.5">
                {s.when && <span className="text-[12.5px] text-fg-2">{s.when}:</span>}
                <StackedBar
                  label={s.when ?? 'Holdings'}
                  height={8}
                  segments={barShares(s.scenario.holdings).map((h, j) => ({
                    key: h.symbol,
                    pct: h.pct,
                    fill: HOLDING_FILLS[j % HOLDING_FILLS.length],
                  }))}
                />
                <span className="font-mono text-[12px] text-fg-2">{holdingWords(s.scenario)}</span>
              </div>
            );
          })}
          {sentences.length > 4 && (
            <span className="text-[12px] text-fg-3">
              {sentences.length - 4} more branches in the rules below.
            </span>
          )}
        </section>
      )}

      <section className="grid gap-3 border-t border-line pt-4">
        <div className="flex items-center justify-between gap-3">
          <span className="kicker">Rules</span>
          <Segmented label="Template view" options={VIEWS} value={view} onChange={setView} />
        </div>
        {view === 'outline' ? (
          parsed ? (
            <div>
              <p className="m-0 mb-3 text-[13px] text-fg-2">
                <Parts
                  parts={metaParts({ timeframe, benchmark: parsed.metadata.benchmark ?? '' })}
                />
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
            <DslCodeBlock
              code={template.configSexpr}
              className="rounded-panel border border-line"
            />
          </Suspense>
        )}
      </section>

      <div className="grid grid-cols-[16px_minmax(0,1fr)] items-start gap-2.5 rounded-panel border border-line bg-sunk/60 px-3.5 py-2.5 text-[12.5px] text-fg-2">
        <Info className="mt-0.5 h-4 w-4 text-fg-3" aria-hidden="true" />
        Templates don’t come with a backtest yet. Use this one, save it, then backtest it over your
        own dates to see how it would have done.
      </div>
    </div>
  );
}
