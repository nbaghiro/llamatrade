import { AlertTriangle, ChevronDown } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import { useDismiss } from '../../ui/useDismiss';

export interface SaveWarning {
  message: string;
  /** Where it is, e.g. "rule 3". */
  where?: string;
  /** Its line in the code, when the rules and the code line up. */
  line?: number | null;
}

export type SaveMode = 'confirm' | 'note';

interface SaveControlProps {
  nextVersion: number;
  /** Problems that stop a save, in words. */
  errors: readonly string[];
  warnings: readonly SaveWarning[];
  /** False when there's nothing to save. */
  canSave: boolean;
  saving: boolean;
  /** True once this draft was just saved and nothing changed since. */
  justSaved: boolean;
  suggestedNote: string;
  /** "The paper session keeps running version 3 until you switch it." */
  sessionLine: string;
  onSave: (note: string) => void;
  /** Opens the confirmation from outside, e.g. on ⌘S with warnings. */
  openRequest?: number;
  /** Opens the code at a warning's line. */
  onGoToLine?: (line: number) => void;
}

/** problems2 A and save2 A: errors block, warnings ask, a clean draft saves at once. */
export function SaveControl({
  nextVersion,
  errors,
  warnings,
  canSave,
  saving,
  justSaved,
  suggestedNote,
  sessionLine,
  onSave,
  openRequest = 0,
  onGoToLine,
}: SaveControlProps) {
  const [mode, setMode] = useState<SaveMode | null>(null);
  const [note, setNote] = useState(suggestedNote);
  const root = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setMode(null), []);
  const refs = useMemo(() => [root], []);
  useDismiss(mode !== null, close, refs);

  const open = useCallback(
    (m: SaveMode) => {
      setNote(suggestedNote);
      setMode(m);
    },
    [suggestedNote]
  );

  useEffect(() => {
    if (openRequest > 0) open('confirm');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest]);

  const blocked = errors.length > 0;
  const disabled = !canSave || saving || blocked;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSave(note.trim());
    setMode(null);
  };

  let label = `Save version ${nextVersion}`;
  if (saving) label = 'Saving';
  else if (justSaved) label = 'Saved';
  else if (blocked)
    label = `Fix ${errors.length} ${errors.length === 1 ? 'problem' : 'problems'} to save`;
  else if (warnings.length > 0)
    label = `Save with ${warnings.length} ${warnings.length === 1 ? 'warning' : 'warnings'}`;

  const primary = !justSaved && !blocked && warnings.length === 0;
  const firstLine = warnings.find((w) => w.line)?.line ?? null;
  return (
    <div ref={root} className="relative flex">
      <button
        type="button"
        disabled={disabled}
        title={blocked ? errors.join(' ') : undefined}
        onClick={() => (warnings.length > 0 ? open('confirm') : onSave(suggestedNote))}
        className={`btn ${primary ? 'btn-primary' : 'btn-secondary'} ${
          warnings.length === 0 && !disabled ? 'rounded-r-none' : ''
        }`}
      >
        {warnings.length > 0 && !blocked && !justSaved && (
          <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        )}
        {label}
      </button>
      {warnings.length === 0 && !disabled && (
        <button
          type="button"
          aria-label="Save with a note"
          aria-expanded={mode === 'note'}
          onClick={() => (mode ? close() : open('note'))}
          className="btn btn-primary rounded-l-none border-l border-l-[rgb(var(--canvas)/0.25)] px-2"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
      )}
      {mode && (
        <form
          role="dialog"
          aria-label={mode === 'confirm' ? 'Save with warnings' : 'Save with a note'}
          onSubmit={submit}
          className="absolute right-0 top-full z-50 mt-2 grid w-[380px] max-w-[calc(100vw-24px)] gap-3 rounded-[12px] border border-line-strong bg-panel p-4 text-left shadow-lg"
        >
          <b className="text-[13.5px] font-semibold text-fg">
            {mode === 'confirm'
              ? `Save version ${nextVersion} with ${warnings.length} ${warnings.length === 1 ? 'warning' : 'warnings'}?`
              : `Save version ${nextVersion}`}
          </b>
          {mode === 'confirm' && (
            <ul className="m-0 grid list-none gap-2 p-0">
              {warnings.map((w, i) => (
                <li key={i} className="grid grid-cols-[16px_minmax(0,1fr)] gap-2 text-[12.5px]">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 text-risk" aria-hidden="true" />
                  <span className="font-mono text-[12px] text-fg">
                    {w.message}
                    {w.line ? (
                      <span className="font-sans text-fg-3"> · line {w.line}</span>
                    ) : (
                      w.where && <span className="font-sans text-fg-3"> · {w.where}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <label className="grid gap-1.5">
            <span className="text-[12px] text-fg-2">Version note</span>
            <input
              autoFocus
              className="input"
              value={note}
              maxLength={300}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <p className="m-0 text-[11.5px] text-fg-3">{sessionLine}</p>
          <div className="flex justify-end gap-2 border-t border-line pt-3">
            {mode === 'confirm' && firstLine !== null && onGoToLine && (
              <button
                type="button"
                className="btn btn-ghost btn-sm mr-auto"
                onClick={() => {
                  close();
                  onGoToLine(firstLine);
                }}
              >
                Go to line {firstLine}
              </button>
            )}
            <button type="button" className="btn btn-secondary btn-sm" onClick={close}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary btn-sm">
              {mode === 'confirm' ? 'Save anyway' : `Save version ${nextVersion}`}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
