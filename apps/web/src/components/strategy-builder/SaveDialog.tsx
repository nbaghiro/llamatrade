import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { Check, Info, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { methodWords, strategySymbols } from '../../lib/outline';
import { diffStrategies, suggestNote } from '../../lib/strategyDiff';
import { useStrategyBuilderStoreWithContext } from '../../store/strategy-builder';
import { Dialog } from '../ui';

import { namedChecks, type NamedCheck } from './codemirror/problemModel';
import type { EngineCheck } from './hooks/useEngineCheck';

interface SaveDialogProps {
  open: boolean;
  onClose: () => void;
  engine: EngineCheck;
  /** The version a running session uses, if one runs. */
  sessionVersion: number | null;
  hasSession: boolean;
  onSaved: (strategyId: string, thenBacktest: boolean) => void;
}

function CheckRow({ check }: { check: NamedCheck }) {
  return (
    <div className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-line py-2 text-[12.5px] last:border-b-0">
      {check.state === 'pass' ? (
        <span className="grid h-4 w-4 place-items-center rounded-full bg-accent-soft text-accent">
          <Check className="h-[11px] w-[11px]" />
        </span>
      ) : check.state === 'fail' ? (
        <span className="grid h-4 w-4 place-items-center rounded-full bg-risk-soft text-risk">
          <X className="h-[11px] w-[11px]" />
        </span>
      ) : (
        <span className="h-3.5 w-3.5 rounded-full border-[1.5px] border-line-strong border-r-accent motion-safe:animate-spin" />
      )}
      <span className={check.state === 'fail' ? 'text-risk' : 'text-fg'}>{check.name}</span>
      <span
        className="max-w-[110px] truncate text-right font-mono text-[11.5px] text-fg-3 sm:max-w-[220px]"
        title={check.detail}
      >
        {check.detail}
      </span>
    </div>
  );
}

/** Save as a new version: the change in words, the engine's checks, a note, and what it means for the session. */
export function SaveDialog({
  open,
  onClose,
  engine,
  sessionVersion,
  hasSession,
  onSaved,
}: SaveDialogProps) {
  const {
    tree,
    timeframe,
    benchmark,
    strategyName,
    savedDsl,
    serverVersion,
    strategyId,
    saving,
    error,
    saveStrategy,
  } = useStrategyBuilderStoreWithContext();
  const nextVersion = strategyId ? serverVersion + 1 : 1;

  const diff = useMemo(() => {
    if (!open || !savedDsl) return null;
    const saved = fromDSLString(savedDsl);
    if (!saved) return null;
    return diffStrategies(
      {
        tree: saved.tree,
        meta: {
          timeframe: saved.metadata.timeframe ?? '1D',
          benchmark: saved.metadata.benchmark ?? '',
        },
      },
      { tree, meta: { timeframe, benchmark } }
    );
  }, [open, savedDsl, tree, timeframe, benchmark]);

  const [note, setNote] = useState('');
  useEffect(() => {
    if (open) setNote(diff ? suggestNote(diff) : strategyId ? '' : 'First version');
  }, [open, diff, strategyId]);

  const checks = useMemo(() => {
    const methods = new Set<string>();
    const indicators = new Set<string>();
    for (const b of Object.values(tree.blocks)) {
      if (b.type === 'weight') methods.add(methodWords(b.method));
      if (b.type === 'if') {
        for (const op of [b.condition.left, b.condition.right]) {
          if (op.type === 'indicator') indicators.add(op.indicator);
        }
      }
    }
    const symbols = strategySymbols(tree, benchmark);
    const errors = engine.status === 'ok' || engine.status === 'problems' ? engine.errors : null;
    return namedChecks(errors, {
      methods: [...methods],
      symbols: [...symbols.held, ...symbols.signals],
      indicators: [...indicators],
    });
  }, [tree, benchmark, engine]);

  const blocked = engine.status === 'problems' || engine.status === 'checking';

  const save = async (withNote: boolean, thenBacktest: boolean) => {
    const id = await saveStrategy(withNote ? note : undefined);
    if (id) onSaved(id, thenBacktest);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width={600}
      title={
        <span className="flex items-baseline gap-2">
          Save version {nextVersion}
          <span className="text-[12px] font-normal text-fg-3">{strategyName}</span>
        </span>
      }
      footer={
        <div className="flex w-full flex-wrap items-center justify-end gap-2">
          <span className="mr-auto min-w-0 flex-1 basis-[140px] text-[12px] text-fg-3">
            Saving doesn’t trade or change any session.
          </span>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => save(false, false)}
            disabled={blocked || saving}
          >
            Save without a note
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => save(true, true)}
            disabled={blocked || saving}
          >
            Save and backtest
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => save(true, false)}
            disabled={blocked || saving}
          >
            {saving ? 'Saving' : `Save version ${nextVersion}`}
          </button>
        </div>
      }
    >
      <div>
        <span className="label">What changed</span>
        {diff ? (
          diff.changes.length ? (
            <ul className="m-0 grid gap-1 pl-4 text-[13.5px]">
              {diff.changes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[13.5px] text-fg-2">
              Nothing has changed since version {serverVersion}.
            </p>
          )
        ) : (
          <p className="m-0 text-[13.5px] text-fg-2">
            {strategyId
              ? 'The saved version couldn’t be read to compare.'
              : 'This is the first version.'}
          </p>
        )}
      </div>

      <div>
        <span className="label">Checks</span>
        {engine.status === 'unavailable' ? (
          <p className="m-0 text-[12.5px] text-fg-2">
            The engine’s checks couldn’t run just now. You can still save, and the backtest checks
            it again.
          </p>
        ) : (
          <div>
            {checks.map((c) => (
              <CheckRow key={c.name} check={c} />
            ))}
          </div>
        )}
        {engine.status === 'problems' && (
          <p className="mb-0 mt-2 text-[12.5px] text-risk">
            Fix the problems in the code before saving.
          </p>
        )}
      </div>

      <label className="grid gap-1.5">
        <span className="text-[12px] text-fg-2">Note for this version</span>
        <input
          className="input"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={300}
        />
      </label>

      <div className="grid grid-cols-[16px_minmax(0,1fr)] gap-2.5 rounded-panel border border-line bg-panel px-3.5 py-2.5 text-[12.5px] text-fg-2">
        <Info className="mt-0.5 h-4 w-4 text-fg-3" aria-hidden="true" />
        <span>
          {hasSession
            ? `The paper session keeps running ${sessionVersion ? `version ${sessionVersion}` : 'the version it started with'}. To run version ${nextVersion}, backtest it and redeploy from the strategy page.`
            : 'No session runs this strategy, so nothing else changes.'}
        </span>
      </div>

      {error && (
        <p role="alert" className="m-0 text-[12.5px] text-risk">
          The version wasn’t saved. {error}
        </p>
      )}
    </Dialog>
  );
}
