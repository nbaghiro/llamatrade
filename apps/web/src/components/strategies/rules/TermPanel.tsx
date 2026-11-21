import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import {
  hasChildren,
  type Block,
  type BlockId,
  type IfBlock,
  type StrategyTree,
} from '@llamatrade/core/strategy/types';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { rebalanceWord } from '../../../lib/outline';
import { nextRebalanceDate } from '../../../lib/sessionState';
import { askCopilotHref } from '../../agent/entry';
import { CopilotMark } from '../../common/Logo';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import { listWords } from '../holdSentences';

import { readingText } from './evaluate';
import { operandWords } from './ruleSentence';
import type { SentenceTerm } from './ruleSentence';
import type { RulesModel } from './useRulesModel';
import { lastChange } from './valueHistory';

const EVERY_UNIT: Record<string, [string, string]> = {
  '1D': ['trading day', 'trading days'],
  '1W': ['week', 'weeks'],
  '1M': ['month', 'months'],
  '3M': ['quarter', 'quarters'],
  '1Y': ['year', 'years'],
};

const EXPLAIN: Record<string, string> = {
  rsi: 'RSI compares recent gains with recent losses on a 0 to 100 scale. Readings above 70 are often called overbought.',
  sma: 'The average daily close over the period.',
  ema: 'An average of daily closes that weights recent days more.',
  momentum: 'The close minus the close the given number of days earlier.',
  price: 'The latest daily close.',
};

function symbolsUnder(tree: StrategyTree, id: BlockId, out: string[] = []): string[] {
  const b = tree.blocks[id];
  if (!b) return out;
  if (b.type === 'asset' && !out.includes(b.symbol)) out.push(b.symbol);
  if (hasChildren(b)) b.childIds.forEach((c) => symbolsUnder(tree, c, out));
  return out;
}

function pairedElse(tree: StrategyTree, ifBlock: IfBlock): BlockId | null {
  const parent = ifBlock.parentId ? tree.blocks[ifBlock.parentId] : undefined;
  if (!parent || !hasChildren(parent)) return null;
  return (
    parent.childIds.find((c) => {
      const b = tree.blocks[c];
      return b?.type === 'else' && b.ifBlockId === ifBlock.id;
    }) ?? null
  );
}

const thresholdOf = (b: Block) => (b.type === 'if' ? operandWords(b.condition.right) : null);
const operandOf = (b: Block) => (b.type === 'if' ? operandWords(b.condition.left) : null);

function Row({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 text-[12.5px] last:border-b-0">
      <span className="text-fg-2">{label}</span>
      <span className="text-right font-mono text-fg">{children}</span>
    </div>
  );
}

function Code({ children }: { children: string }) {
  return (
    <pre className="m-0 mt-3 overflow-x-auto whitespace-pre-wrap rounded-[6px] bg-sunk px-3 py-2.5 font-mono text-[12px] leading-[1.6] text-fg-2">
      {children}
    </pre>
  );
}

/** What one term of the sentence means: its code, today's reading and its history. */
export function TermPanel({
  term,
  model,
  strategy,
  onClose,
  compact = false,
}: {
  term: SentenceTerm;
  model: RulesModel;
  strategy: Strategy;
  onClose: () => void;
  compact?: boolean;
}) {
  const { tree, fragments, readings, versionTrees, timeframe } = model;
  const t = term.target;
  const [one, many] = EVERY_UNIT[timeframe] ?? ['rebalance', 'rebalances'];
  const editHref = (rule: number, field: string) =>
    `/strategies/${strategy.id}/edit?focus=${rule}&field=${encodeURIComponent(field)}`;

  let kicker = '';
  let code: string | null = null;
  const rows: Array<{ label: ReactNode; value: ReactNode }> = [];
  let note: string | null = null;
  let edit: string | null = null;
  let symbolList: string[] = [];

  if (!tree) return null;

  if (t.kind === 'condition') {
    const block = tree.blocks[t.blockId];
    if (block?.type !== 'if') return null;
    const c = block.condition;
    kicker =
      t.part === 'threshold'
        ? `Rule ${t.rule}, the line it's checked against`
        : `Rule ${t.rule}, what it reads`;
    code = fragments.get(block.id) ?? null;
    const r = readings.status === 'ready' ? readings.byBlock.get(block.id) : undefined;
    const subject = operandWords(c.left);
    if (r?.today) {
      const side =
        r.today.value > r.today.against
          ? 'above'
          : r.today.value < r.today.against
            ? 'below'
            : 'at';
      rows.push({ label: `${subject} today`, value: `${readingText(r.today.value)}, ${side}` });
      const sideId = r.today.holds ? block.id : pairedElse(tree, block);
      const syms = sideId ? symbolsUnder(tree, sideId) : [];
      rows.push({
        label: 'So today this rule picks',
        value: syms.length ? listWords(syms) : 'nothing',
      });
      const n = r.rebalances;
      rows.push({
        label: `It held ${r.window.source === 'backtest' ? 'over the backtest' : 'in the last two years'}`,
        value: `${n.held} of ${n.total} ${n.total === 1 ? one : many}`,
      });
    } else {
      rows.push({
        label: `${subject} today`,
        value:
          readings.status === 'loading'
            ? 'Reading…'
            : readings.status === 'error'
              ? 'Prices didn’t load'
              : 'Not read on this page',
      });
    }
    const change = lastChange(
      versionTrees,
      block.id,
      t.part === 'threshold' ? thresholdOf : operandOf
    );
    rows.push(
      change
        ? { label: `Changed in version ${change.version}`, value: `was ${change.was}` }
        : { label: 'Changed', value: versionTrees.length > 1 ? 'Not since version 1' : 'Version 1' }
    );
    const op = c.left;
    note =
      op.type === 'indicator'
        ? (EXPLAIN[op.indicator] ?? null)
        : op.type === 'price'
          ? EXPLAIN.price
          : null;
    if (!r?.today && readings.status === 'none') {
      note = `${note ? `${note} ` : ''}This page reads prices and close-based indicators only, so the session works this one out at its rebalance.`;
    }
    edit = editHref(t.rule, t.field);
  } else if (t.kind === 'holding') {
    const block = tree.blocks[t.blockId];
    kicker = 'A holding';
    code = fragments.get(t.blockId) ?? null;
    if (t.pct !== null)
      rows.push({ label: 'Weight in its branch', value: `${readingText(t.pct)}%` });
    const pctOf = (b: Block, tr: StrategyTree) => {
      if (b.type !== 'asset' || !b.parentId) return null;
      const parent = tr.blocks[b.parentId];
      return parent?.type === 'weight' && parent.method === 'specified'
        ? `${readingText(parent.allocations[b.id] ?? 0)}%`
        : null;
    };
    if (block) {
      const change = lastChange(versionTrees, block.id, pctOf);
      if (change)
        rows.push({ label: `Changed in version ${change.version}`, value: `was ${change.was}` });
    }
    if (t.rule !== null) edit = editHref(t.rule, 'asset.weight');
  } else if (t.kind === 'pick') {
    kicker = `Rule ${t.rule}`;
    code = fragments.get(t.blockId) ?? null;
    edit = editHref(t.rule, t.field);
    note = 'Ranked again at every rebalance, so which funds it holds can change each time.';
  } else if (t.kind === 'rebalance') {
    kicker = 'When it rebalances';
    code = `:rebalance ${rebalanceWord(timeframe)}`;
    const next = nextRebalanceDate(rebalanceWord(timeframe), etToday());
    rows.push({ label: 'Next rebalance', value: next ? dayLabel(next) : 'Each trading day' });
    note = 'The rules are checked on the first daily bar of each period, and orders go in then.';
    edit = `/strategies/${strategy.id}/edit`;
  } else {
    kicker = 'Folded in the sentence';
    const isRules = t.of === 'rules';
    if (isRules) {
      for (const r of t.rules) rows.push({ label: `Rule ${r.number}`, value: r.text });
    } else {
      symbolList = t.rules.map((r) => r.text);
      kicker = 'The funds it chooses from';
    }
    if (isRules && t.rules.length > 0) {
      const first = t.rules[0].number;
      const last = t.rules[t.rules.length - 1].number;
      note =
        first === last
          ? `Rule ${first} in the outline.`
          : `Rules ${first} to ${last} in the outline.`;
    }
  }

  const ask = askCopilotHref(
    `In ${strategy.name}, what does “${term.text}” do, and how has it affected results?`,
    `strategy:${strategy.id}`,
    { send: true }
  );

  return (
    <section
      className={compact ? 'grid gap-1' : 'panel-rim grid gap-1 px-5 py-4'}
      aria-label={`About ${term.text}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="kicker">{kicker}</span>
          <div className="mt-1 text-[18px] font-semibold tracking-[-0.01em]">{term.text}</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="-mr-1 rounded-[6px] p-1 text-fg-3 hover:bg-sunk hover:text-fg"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {code && <Code>{code}</Code>}
      {rows.length > 0 && (
        <div className="mt-2">
          {rows.map((r, i) => (
            <Row key={i} label={r.label}>
              {r.value}
            </Row>
          ))}
        </div>
      )}
      {symbolList.length > 0 && (
        <p className="m-0 mt-2 font-mono text-[12.5px] leading-[1.8] text-fg">
          {symbolList.join(' ')}
        </p>
      )}
      {note && <p className="m-0 mt-2 text-[12.5px] leading-[1.55] text-fg-2">{note}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {edit && (
          <Link
            to={edit}
            className={`btn btn-primary btn-sm ${compact ? 'w-full justify-center' : ''}`}
          >
            Change the value
          </Link>
        )}
        {!compact && (
          <Link to={ask} className="btn btn-secondary btn-sm">
            <CopilotMark size={14} />
            Ask Copilot
          </Link>
        )}
      </div>
    </section>
  );
}
