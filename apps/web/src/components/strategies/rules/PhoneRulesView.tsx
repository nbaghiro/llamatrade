import type { BlockId, ConditionExpression, StrategyTree } from '@llamatrade/core/strategy/types';
import { Minus, Plus, X } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { monthYear } from '../strategyView';

import { readingText } from './evaluate';
import { phoneNote, stepFor } from './phoneEdit';
import { operandWords, ruleSentence, type SentenceTerm } from './ruleSentence';
import { RuleSentenceView } from './RuleSentenceView';
import { useRuleReadings } from './useRuleReadings';

function Sheet({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-[70] flex items-end"
      style={{ background: 'var(--scrim)' }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[85vh] w-full overflow-y-auto rounded-t-[18px] border-t border-line-strong bg-panel px-5 pb-8 pt-2 shadow-xl"
      >
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-line-strong" />
        {children}
      </div>
    </div>
  );
}

/** The indicator's recent history with the saved line dashed and the new one solid. */
function LineHistory({
  values,
  saved,
  now,
}: {
  values: readonly number[];
  saved: number;
  now: number;
}) {
  const finite = values.filter(Number.isFinite);
  if (finite.length < 2) return null;
  const lo = Math.min(...finite, saved, now);
  const hi = Math.max(...finite, saved, now);
  const W = 320;
  const H = 96;
  const y = (v: number) => H - ((v - lo) / (hi - lo || 1)) * (H - 8) - 4;
  const step = W / (values.length - 1);
  let d = '';
  let pen = false;
  values.forEach((v, i) => {
    if (!Number.isFinite(v)) {
      pen = false;
      return;
    }
    d += `${pen ? 'L' : 'M'}${(i * step).toFixed(1)},${y(v).toFixed(1)} `;
    pen = true;
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-24 w-full" aria-hidden="true">
      <path d={d} fill="none" stroke="rgb(var(--accent))" strokeWidth="1.4" />
      <line
        x1="0"
        x2={W}
        y1={y(saved)}
        y2={y(saved)}
        stroke="rgb(var(--fg-3))"
        strokeDasharray="4 3"
      />
      <line x1="0" x2={W} y1={y(now)} y2={y(now)} stroke="rgb(var(--fg))" strokeWidth="1.2" />
    </svg>
  );
}

interface PhoneRulesViewProps {
  name: string;
  tree: StrategyTree;
  timeframe: string;
  /** The tree as last saved, to read each value's saved setting from. */
  savedTree: StrategyTree | null;
  nextVersion: number;
  saving: boolean;
  onCondition: (blockId: BlockId, condition: ConditionExpression) => void;
  onSave: (note: string) => void;
  onRevert: () => void;
}

/**
 * The editor on a phone (phone2 A): the rules read as a sentence, and one value changed at a
 * time from a sheet with its history. Adding or removing rules stays on a computer.
 */
export function PhoneRulesView({
  name,
  tree,
  timeframe,
  savedTree,
  nextVersion,
  saving,
  onCondition,
  onSave,
  onRevert,
}: PhoneRulesViewProps) {
  const sentence = useMemo(() => ruleSentence(tree, timeframe), [tree, timeframe]);
  const readings = useRuleReadings(savedTree ?? tree, timeframe, null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [openTerm, setOpenTerm] = useState<SentenceTerm | null>(null);
  const open = (id: string) => {
    setOpenId(id);
    setOpenTerm(
      sentence.parts.find((p): p is SentenceTerm => p.kind === 'term' && p.id === id) ?? null
    );
  };
  const close = () => {
    setOpenId(null);
    setOpenTerm(null);
  };

  const t = openTerm?.target;
  const block = t && t.kind === 'condition' ? tree.blocks[t.blockId] : undefined;
  const condition = block?.type === 'if' ? block.condition : null;
  const editable = t?.kind === 'condition' && condition?.right.type === 'number' ? condition : null;
  const savedIndex = useMemo(() => {
    if (!savedTree) return new Map<number, BlockId>();
    const ifs = Object.values(savedTree.blocks).filter((b) => b.type === 'if');
    return new Map(ifs.map((b, i) => [i, b.id]));
  }, [savedTree]);
  const ifOrder = Object.values(tree.blocks)
    .filter((b) => b.type === 'if')
    .map((b) => b.id);
  const savedId = block ? savedIndex.get(ifOrder.indexOf(block.id)) : undefined;
  const savedBlock = savedId && savedTree ? savedTree.blocks[savedId] : undefined;
  const savedValue =
    savedBlock?.type === 'if' && savedBlock.condition.right.type === 'number'
      ? savedBlock.condition.right.value
      : null;
  const reading =
    savedId && readings.status === 'ready' ? readings.byBlock.get(savedId) : undefined;

  const setValue = (v: number) => {
    if (!editable || !block || editable.right.type !== 'number') return;
    onCondition(block.id, {
      ...editable,
      right: { ...editable.right, value: Math.round(v * 100) / 100 },
    });
  };
  const value = editable && editable.right.type === 'number' ? editable.right.value : null;
  const changed = value !== null && savedValue !== null && value !== savedValue;

  return (
    <section className="grid gap-3">
      <span className="text-[12px] text-fg-3">Tap a part to change it</span>
      <RuleSentenceView
        parts={sentence.parts}
        openId={openId}
        onOpen={open}
        className="text-[17px] leading-[1.7] text-fg-2"
      />
      {openTerm && (
        <Sheet onClose={close}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="kicker">{name}</span>
              <div className="mt-1 text-[16px] font-semibold">
                {editable ? `Rule ${t?.kind === 'condition' ? t.rule : ''} line` : openTerm.text}
              </div>
            </div>
            <span className="flex items-center gap-2">
              {savedValue !== null && changed && (
                <span className="font-mono text-[11.5px] text-fg-3">
                  was {readingText(savedValue)}
                </span>
              )}
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="rounded-[6px] p-1 text-fg-3 hover:bg-sunk hover:text-fg"
              >
                <X className="h-4 w-4" />
              </button>
            </span>
          </div>
          {editable && value !== null ? (
            <div className="mt-4 grid gap-3">
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  aria-label="Lower"
                  onClick={() => setValue(value - stepFor(value))}
                  className="grid h-10 w-10 place-items-center rounded-[10px] border border-line-strong"
                >
                  <Minus className="h-4 w-4" />
                </button>
                <span className="font-mono text-[28px] font-semibold">{readingText(value)}</span>
                <button
                  type="button"
                  aria-label="Raise"
                  onClick={() => setValue(value + stepFor(value))}
                  className="grid h-10 w-10 place-items-center rounded-[10px] border border-line-strong"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>
              {reading && (
                <>
                  <LineHistory
                    values={reading.history.left.slice(-504)}
                    saved={savedValue ?? value}
                    now={value}
                  />
                  <span className="flex justify-between text-[11.5px] text-fg-3">
                    <span>
                      {operandWords(editable.left)}
                      {reading.history.dates.length > 0 &&
                        `, ${monthYear(reading.history.dates[Math.max(0, reading.history.dates.length - 504)])} to ${monthYear(reading.history.dates[reading.history.dates.length - 1])}`}
                    </span>
                    <span>dashed {readingText(savedValue ?? value)}</span>
                  </span>
                </>
              )}
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  className="btn btn-secondary justify-center"
                  onClick={() => {
                    if (savedValue !== null) setValue(savedValue);
                    onRevert();
                    close();
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary justify-center"
                  disabled={!changed || saving}
                  onClick={() => {
                    if (savedValue === null || t?.kind !== 'condition') return;
                    onSave(phoneNote(t.rule, savedValue, value));
                    close();
                  }}
                >
                  {saving ? 'Saving…' : `Save version ${nextVersion}`}
                </button>
              </div>
            </div>
          ) : (
            <p className="m-0 mt-3 text-[13px] leading-[1.55] text-fg-2">
              This part can be changed in the editor on a computer, or by asking Copilot. On a phone
              you can change the numbers a rule checks against.
            </p>
          )}
        </Sheet>
      )}
    </section>
  );
}
