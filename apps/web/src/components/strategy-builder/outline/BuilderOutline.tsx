import type { BlockId, ConditionExpression, WeightMethod } from '@llamatrade/core/strategy/types';
import { Plus, X } from 'lucide-react';
import { useCallback, useMemo, useRef, useState, type FormEvent } from 'react';

import {
  allocationProblem,
  applyTokenEdit,
  buildOutline,
  isValidSymbol,
  metaParts,
  normaliseSymbol,
  OUTLINE_MAX_DEPTH,
  type OutlineToken,
} from '../../../lib/outline';
import type { StrategyDiff } from '../../../lib/strategyDiff';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { Popover } from '../../ui';
import { useDismiss } from '../../ui/useDismiss';

import { Outline, Parts, type AnyLine } from './Outline';

const DEFAULT_CONDITION: ConditionExpression = {
  left: { type: 'indicator', indicator: 'rsi', period: 14, symbol: 'SPY' },
  comparator: 'gt',
  right: { type: 'number', value: 70 },
};

const CONTAINERS = new Set(['weight', 'if', 'else', 'group', 'filter']);

interface BuilderOutlineProps {
  /** A tracked change to show in place of the editable outline, e.g. a Copilot proposal. */
  tracked?: StrategyDiff | null;
  readOnly?: boolean;
}

export function BuilderOutline({ tracked, readOnly = false }: BuilderOutlineProps) {
  const store = useStrategyBuilderStoreWithContext();
  const { tree, timeframe, benchmark, ui } = store;
  const [expanded, setExpanded] = useState<ReadonlySet<BlockId>>(new Set());

  const lines = useMemo(
    () => buildOutline(tree, { maxDepth: OUTLINE_MAX_DEPTH, expanded }),
    [tree, expanded]
  );
  const meta = useMemo(() => metaParts({ timeframe, benchmark }), [timeframe, benchmark]);

  const notes = useMemo(() => {
    const out = new Map<string, string>();
    for (const b of Object.values(tree.blocks)) {
      if (b.type !== 'weight') continue;
      const problem = allocationProblem(tree, b.id);
      if (problem) out.set(b.id, problem);
    }
    return out;
  }, [tree]);

  const onEdit = useCallback(
    (token: OutlineToken, raw: string): string | null => {
      const edit = applyTokenEdit(tree, token, raw);
      switch (edit.kind) {
        case 'invalid':
          return edit.reason;
        case 'condition':
          store.updateCondition(edit.blockId, edit.condition);
          return null;
        case 'block':
          store.updateBlock(edit.blockId, edit.updates);
          return null;
        case 'filter':
          store.updateFilter(edit.blockId, edit.config);
          return null;
        case 'allocation':
          store.setWeightAllocation(edit.weightId, edit.childId, edit.percent);
          return null;
        case 'timeframe':
          store.setTimeframe(edit.value);
          return null;
        case 'benchmark':
          store.setBenchmark(edit.value);
          return null;
      }
    },
    [tree, store]
  );

  const remove = useCallback(
    (blockId: BlockId) => {
      const block = tree.blocks[blockId];
      if (!block) return;
      if (block.type === 'if' && block.parentId) {
        const parent = tree.blocks[block.parentId];
        const pairedElse =
          parent && 'childIds' in parent
            ? parent.childIds.find((id) => {
                const b = tree.blocks[id];
                return b?.type === 'else' && b.ifBlockId === blockId;
              })
            : undefined;
        if (pairedElse) store.deleteBlock(pairedElse);
      }
      store.deleteBlock(blockId);
    },
    [tree, store]
  );

  const lineActions = useCallback(
    (line: AnyLine) => (
      <>
        {CONTAINERS.has(line.kind) && line.kind !== 'filter' && (
          <AddHolding
            onAdd={(symbol) => store.addAsset(line.blockId, symbol, '', symbol)}
            label={line.number ? `Add a holding to rule ${line.number}` : 'Add a holding'}
          />
        )}
        {line.kind !== 'else' && (
          <button
            type="button"
            aria-label={
              line.kind === 'asset' ? `Remove ${line.symbol}` : `Delete rule ${line.number}`
            }
            onClick={(e) => {
              e.stopPropagation();
              remove(line.blockId);
            }}
            className="grid h-6 w-6 place-items-center rounded-[5px] text-fg-3 hover:bg-sunk hover:text-fg"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </>
    ),
    [store, remove]
  );

  const selected = ui.selectedBlockId ? tree.blocks[ui.selectedBlockId] : undefined;
  const target =
    selected && CONTAINERS.has(selected.type) && selected.type !== 'filter'
      ? selected.id
      : tree.rootId;
  const targetNumber =
    target !== tree.rootId ? lines.find((l) => l.blockId === target)?.number : null;

  const addRule = (kind: WeightMethod | 'if') => {
    if (kind === 'if') store.addCondition(target, DEFAULT_CONDITION);
    else store.addWeight(target, kind);
  };

  const editable = !readOnly && !tracked;
  return (
    <div>
      <p className="m-0 flex flex-wrap items-center gap-y-1 text-[13.5px] text-fg-2">
        <Parts parts={tracked ? tracked.meta : meta} onEdit={editable ? onEdit : undefined} />
      </p>
      <div className="mt-5">
        {tracked ? (
          <Outline lines={tracked.lines} label="Strategy outline with the proposed change" />
        ) : (
          <Outline
            lines={lines}
            label="Strategy outline"
            onEdit={editable ? onEdit : undefined}
            onExpand={(id) => setExpanded((s) => new Set(s).add(id))}
            selectedId={editable ? ui.selectedBlockId : null}
            onSelect={
              editable
                ? (id) => store.selectBlock(ui.selectedBlockId === id ? null : id)
                : undefined
            }
            lineActions={editable ? lineActions : undefined}
            notes={notes}
          />
        )}
      </div>
      {lines.length === 0 && !tracked && (
        <p className="m-0 py-6 text-center text-[13px] text-fg-3">
          Nothing here yet. Add a rule to say what the strategy holds.
        </p>
      )}
      {editable && (
        <div className="pl-[32px] pt-3 sm:pl-[42px]">
          <Popover
            align="left"
            width={280}
            role="menu"
            label="Add a rule"
            trigger={(p) => (
              <button
                type="button"
                {...p}
                className="flex items-center gap-2 text-[13px] text-accent hover:underline"
              >
                <Plus className="h-4 w-4" />
                {targetNumber ? `Add a rule inside rule ${targetNumber}` : 'Add a rule'}
              </button>
            )}
          >
            {(close) => (
              <div className="grid p-1.5">
                {(
                  [
                    ['specified', 'Hold fixed weights', 'You set each holding’s percentage.'],
                    ['equal', 'Hold at equal weight', 'Every holding gets the same share.'],
                    ['momentum', 'Weight by momentum', 'Stronger recent performers get more.'],
                    [
                      'inverse_volatility',
                      'Weight by inverse volatility',
                      'Calmer holdings get more.',
                    ],
                    [
                      'if',
                      'A condition, with an otherwise',
                      'Hold one thing when a rule is met, another when not.',
                    ],
                  ] as const
                ).map(([kind, title, hint]) => (
                  <button
                    key={kind}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      addRule(kind);
                      close();
                    }}
                    className="grid gap-0.5 rounded-[6px] px-2 py-[7px] text-left hover:bg-sunk"
                  >
                    <span className="text-[13px] text-fg">{title}</span>
                    <span className="text-[12px] text-fg-3">{hint}</span>
                  </button>
                ))}
              </div>
            )}
          </Popover>
        </div>
      )}
    </div>
  );
}

function AddHolding({ onAdd, label }: { onAdd: (symbol: string) => void; label: string }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLSpanElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    setValue('');
    setError(null);
  }, []);
  const refs = useMemo(() => [root], []);
  useDismiss(open, close, refs);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!isValidSymbol(value)) {
      setError('Enter a ticker, for example VTI.');
      return;
    }
    onAdd(normaliseSymbol(value));
    close();
  };

  return (
    <span ref={root} className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="grid h-6 w-6 place-items-center rounded-[5px] text-fg-3 hover:bg-sunk hover:text-fg"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
      {open && (
        <form
          onSubmit={submit}
          className="absolute right-0 top-full z-30 mt-1.5 grid w-[220px] gap-2 rounded-[10px] border border-line-strong bg-panel p-2 text-left shadow-lg"
        >
          <label className="text-[12px] text-fg-2" htmlFor="add-holding">
            {label}
          </label>
          <input
            id="add-holding"
            autoFocus
            value={value}
            onChange={(e) => {
              setError(null);
              setValue(e.target.value.toUpperCase());
            }}
            placeholder="VTI"
            className={`input h-8 font-mono ${error ? 'input-error' : ''}`}
          />
          {error && <span className="text-[12px] text-risk">{error}</span>}
          <button type="submit" className="btn btn-primary btn-sm justify-self-end">
            Add
          </button>
        </form>
      )}
    </span>
  );
}
