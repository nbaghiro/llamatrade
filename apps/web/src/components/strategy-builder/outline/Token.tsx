import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import type { OutlineToken } from '../../../lib/outline';
import type { DiffToken } from '../../../lib/strategyDiff';
import { useDismiss } from '../../ui/useDismiss';

import { tokenKey } from './tokenKey';

/** Returns an error sentence, or null when the edit applied. */
export type TokenEditHandler = (token: OutlineToken, raw: string) => string | null;
/** Returns true when it handled the click itself, so the small popover stays closed. */
export type TokenOpenHandler = (token: OutlineToken) => boolean;

const BASE =
  'mx-px inline-block rounded-[3px] px-[5px] tabular-nums leading-[1.45] transition-shadow';
const IDLE = 'bg-sunk text-fg shadow-[inset_0_-1px_0_rgb(var(--line-strong))]';
const OPEN =
  'bg-canvas text-fg shadow-[inset_0_0_0_1px_rgb(var(--accent)),0_0_0_3px_var(--accent-soft)]';
const BAD = 'bg-sunk text-risk shadow-[inset_0_-1.5px_0_rgb(var(--risk))]';
const WAS = 'bg-hatch text-fg-3 line-through decoration-fg-3';
const NOW = 'bg-accent-soft text-accent shadow-[inset_0_0_0_1px_rgb(var(--accent)/0.5)]';

export function TrackedWas({ children }: { children: string }) {
  return (
    <span className={`${BASE} ${WAS}`}>
      <span className="sr-only">was </span>
      {children}
    </span>
  );
}

interface TokenProps {
  token: OutlineToken | DiffToken;
  onEdit?: TokenEditHandler;
  onOpen?: TokenOpenHandler;
  openKey?: string | null;
}

/** A value in the outline. Editable tokens open a small editor in place. */
export function Token({ token, onEdit, onOpen, openKey }: TokenProps) {
  const was = 'was' in token ? token.was : undefined;
  if (was !== undefined && onEdit) {
    return (
      <>
        <EditableToken token={token} onEdit={onEdit} onOpen={onOpen} openKey={openKey} />
        <span className="ml-0.5 font-mono text-[0.85em] text-fg-3 line-through decoration-fg-3">
          <span className="sr-only">was </span>
          {was}
        </span>
      </>
    );
  }
  if (was !== undefined) {
    return (
      <>
        <TrackedWas>{was}</TrackedWas>
        <span className={`${BASE} ${NOW}`}>
          <span className="sr-only">now </span>
          {token.text}
        </span>
      </>
    );
  }
  if (!onEdit) return <span className={`${BASE} ${token.bad ? BAD : IDLE}`}>{token.text}</span>;
  return <EditableToken token={token} onEdit={onEdit} onOpen={onOpen} openKey={openKey} />;
}

function EditableToken({
  token,
  onEdit,
  onOpen,
  openKey,
}: {
  token: OutlineToken;
  onEdit: TokenEditHandler;
  onOpen?: TokenOpenHandler;
  openKey?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {
    if (root.current?.contains(document.activeElement)) button.current?.focus();
    setOpen(false);
  }, []);
  const refs = useMemo(() => [root], []);
  useDismiss(open, close, refs);

  return (
    <span ref={root} className="relative inline-block">
      <button
        ref={button}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open || openKey === tokenKey(token)}
        onClick={() => {
          if (!open && onOpen?.(token)) return;
          setOpen((o) => !o);
        }}
        className={`${BASE} ${open || openKey === tokenKey(token) ? OPEN : token.bad ? BAD : IDLE} cursor-pointer hover:shadow-[inset_0_0_0_1px_rgb(var(--line-strong))]`}
      >
        {token.text}
      </button>
      {open && <TokenEditorPanel token={token} onEdit={onEdit} onDone={close} />}
    </span>
  );
}

function TokenEditorPanel({
  token,
  onEdit,
  onDone,
}: {
  token: OutlineToken;
  onEdit: TokenEditHandler;
  onDone: () => void;
}) {
  const [value, setValue] = useState(token.value);
  const [error, setError] = useState<string | null>(null);
  const editor = token.editor;
  const list = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const options = list.current?.querySelectorAll<HTMLButtonElement>('[role=option]');
    if (!options?.length) return;
    const current = [...options].find((o) => o.getAttribute('aria-selected') === 'true');
    (current ?? options[0]).focus();
  }, []);

  const apply = (raw: string) => {
    const err = onEdit(token, raw);
    if (err) setError(err);
    else onDone();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    apply(value);
  };

  return (
    <span
      role="dialog"
      aria-label="Edit value"
      className="absolute left-0 top-full z-30 mt-1.5 block w-[240px] max-w-[calc(100vw-32px)] rounded-[10px] border border-line-strong bg-panel p-2 text-left text-[13px] font-normal leading-normal text-fg shadow-lg"
    >
      {editor.type === 'choice' ? (
        <span ref={list} role="listbox" className="grid max-h-[260px] gap-0.5 overflow-y-auto">
          {editor.options.map((o) => {
            const on = o.value === token.value;
            return (
              <button
                key={o.value}
                type="button"
                role="option"
                aria-selected={on}
                onClick={() => apply(o.value)}
                className={`rounded-[6px] px-2 py-1.5 text-left ${on ? 'bg-accent-soft text-accent' : 'text-fg-2 hover:bg-sunk hover:text-fg'}`}
              >
                {o.label}
              </button>
            );
          })}
          {error && <span className="px-2 pt-1 text-[12px] text-risk">{error}</span>}
        </span>
      ) : (
        <form onSubmit={submit} className="grid gap-2">
          <span className="flex items-center gap-2">
            <input
              autoFocus
              value={value}
              inputMode={editor.type === 'number' ? 'decimal' : 'text'}
              onChange={(e) => {
                setError(null);
                setValue(editor.type === 'symbol' ? e.target.value.toUpperCase() : e.target.value);
              }}
              placeholder={editor.type === 'symbol' && editor.optional ? 'None' : undefined}
              aria-invalid={error !== null}
              className={`input h-8 font-mono ${error ? 'input-error' : ''}`}
            />
            {editor.type === 'number' && editor.suffix && (
              <span className="text-fg-3">{editor.suffix}</span>
            )}
          </span>
          {error && <span className="text-[12px] text-risk">{error}</span>}
          <span className="flex justify-end gap-1.5">
            <button type="button" onClick={onDone} className="btn btn-ghost btn-sm">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary btn-sm">
              Apply
            </button>
          </span>
        </form>
      )}
    </span>
  );
}
