import type { WatchItem } from '@llamatrade/core/stores/markets';
import { useEffect, useMemo, useRef, useState } from 'react';


interface SymbolPickerProps {
  value: string;
  options: WatchItem[];
  onSelect: (symbol: string) => void;
}

const TICKER = /^[A-Z.]{1,6}$/;

/** Searchable `SYMBOL ▾` selector over the watchlist, with a typed-ticker fallback. */
export default function SymbolPicker({ value, options, onSelect }: SymbolPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else setQuery('');
  }, [open]);

  const q = query.trim().toUpperCase();
  const filtered = useMemo(() => {
    if (!q) return options;
    return options.filter(
      (o) => o.symbol.includes(q) || o.name.toUpperCase().includes(q)
    );
  }, [options, q]);

  const canLoadTyped = q.length > 0 && TICKER.test(q) && !filtered.some((o) => o.symbol === q);

  const choose = (symbol: string) => {
    onSelect(symbol);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[0]) choose(filtered[0].symbol);
      else if (canLoadTyped) choose(q);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 font-mono font-bold text-[22px] leading-none tracking-[-0.01em] hover:text-orange-500 transition-colors"
      >
        {value || '—'}
        <span className="text-[12px] text-ink/40" aria-hidden>
          ▾
        </span>
      </button>

      {open && (
        <div className="absolute z-50 mt-2 w-64 bg-paper border-2 border-ink shadow-[4px_4px_0_rgb(var(--lt-ink))]">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search symbol…"
            className="w-full bg-paper border-b-2 border-ink px-3 py-2 font-mono text-[12px] uppercase tracking-[0.04em] focus:outline-none placeholder:normal-case placeholder:tracking-normal placeholder:text-ink/35"
          />
          <div className="max-h-64 overflow-y-auto">
            {filtered.map((o) => (
              <button
                key={o.symbol}
                onClick={() => choose(o.symbol)}
                className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left transition-colors hover:bg-ink/5 ${
                  o.symbol === value ? 'bg-ink/[0.04]' : ''
                }`}
              >
                <span className="flex items-baseline gap-2 min-w-0">
                  <span className="font-mono font-bold text-[12px] tracking-[0.02em]">
                    {o.symbol}
                  </span>
                  {o.name && (
                    <span className="font-mono text-[10px] text-ink/45 truncate">{o.name}</span>
                  )}
                </span>
                {o.held && (
                  <span className="shrink-0 font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-bone bg-ink px-1 py-0.5">
                    held
                  </span>
                )}
              </button>
            ))}

            {canLoadTyped && (
              <button
                onClick={() => choose(q)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left border-t-2 border-ink hover:bg-ink/5 transition-colors"
              >
                <span className="font-mono text-[11px] font-bold uppercase tracking-[0.05em] text-orange-500">
                  Load {q} →
                </span>
              </button>
            )}

            {filtered.length === 0 && !canLoadTyped && (
              <div className="px-3 py-3 font-mono text-[11px] text-ink/40">No matches</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
