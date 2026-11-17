import { useEffect, useState, type ReactNode } from 'react';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid min-w-0 gap-1.5">
      <span className="text-[12px] text-fg-2">{label}</span>
      {children}
    </label>
  );
}

/** Text input that commits on Enter or blur and shows a reason when the value is refused. */
export function CommitInput({
  value,
  onCommit,
  className = '',
  suffix,
  inputMode = 'text',
  ariaLabel,
}: {
  value: string;
  onCommit: (raw: string) => string | null;
  className?: string;
  suffix?: string;
  inputMode?: 'text' | 'decimal' | 'numeric';
  ariaLabel: string;
}) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    if (draft === value) return;
    const err = onCommit(draft);
    setError(err);
    if (err) setDraft(value);
  };
  return (
    <span className="grid gap-1">
      <span className="relative">
        <input
          aria-label={ariaLabel}
          value={draft}
          inputMode={inputMode}
          aria-invalid={error !== null}
          onChange={(e) => {
            setError(null);
            setDraft(e.target.value);
          }}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
          }}
          className={`input h-9 font-mono ${error ? 'input-error' : ''} ${suffix ? 'pr-11' : ''} ${className}`}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-fg-3">
            {suffix}
          </span>
        )}
      </span>
      {error && <span className="text-[11.5px] text-risk">{error}</span>}
    </span>
  );
}

export function NumberCell({
  value,
  onCommit,
  label,
  suffix,
  min,
  max,
  integer,
}: {
  value: number;
  onCommit: (v: number) => void;
  label: string;
  suffix?: string;
  min: number;
  max: number;
  integer: boolean;
}) {
  const [draft, setDraft] = useState(String(value));
  const [bad, setBad] = useState(false);
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => {
    const v = Number(draft);
    const ok = draft.trim() !== '' && Number.isFinite(v) && v >= min && v <= max;
    if (!ok || (integer && !Number.isInteger(v))) {
      setBad(true);
      setDraft(String(value));
      return;
    }
    setBad(false);
    if (v !== value) onCommit(v);
  };
  return (
    <span className="relative inline-block w-[110px]">
      <input
        aria-label={label}
        value={draft}
        inputMode="decimal"
        aria-invalid={bad}
        onChange={(e) => {
          setBad(false);
          setDraft(e.target.value);
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit();
        }}
        className={`input h-9 pr-8 font-mono ${bad ? 'input-error' : ''}`}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-fg-3">
          {suffix}
        </span>
      )}
    </span>
  );
}
