import type { WatchItem } from '@llamatrade/core/stores/markets';
import { ChevronDown } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

interface SymbolPickerProps {
  value: string;
  options: WatchItem[];
  onSelect: (symbol: string) => void;
}

const TICKER = /^[A-Z.]{1,6}$/;

/** Searchable symbol selector over the watchlist, which also loads a typed ticker. */
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
    return options.filter((o) => o.symbol.includes(q) || o.name.toUpperCase().includes(q));
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
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-[6px] px-1 py-0.5 font-mono text-[18px] font-medium tracking-[-0.01em] text-fg hover:bg-sunk"
      >
        {value || 'Symbol'}
        <ChevronDown aria-hidden="true" className="h-4 w-4 text-fg-3" />
      </button>

      {open && (
        <div className="dropdown left-0 mt-1.5 w-64 py-0">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search or type a ticker"
            aria-label="Search symbols"
            className="w-full border-b border-line bg-panel px-3 py-2 text-[13px] text-fg placeholder:text-fg-3 focus:outline-none"
          />
          <div className="max-h-64 overflow-y-auto py-1" role="listbox" aria-label="Symbols">
            {filtered.map((o) => (
              <button
                key={o.symbol}
                type="button"
                role="option"
                aria-selected={o.symbol === value}
                onClick={() => choose(o.symbol)}
                className={`dropdown-item justify-between ${o.symbol === value ? 'bg-sunk text-fg' : ''}`}
              >
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className="font-mono text-[12.5px] font-medium text-fg">{o.symbol}</span>
                  {o.name && <span className="truncate text-[11.5px] text-fg-3">{o.name}</span>}
                </span>
                {o.held && <span className="badge">Held</span>}
              </button>
            ))}
            {canLoadTyped && (
              <button
                type="button"
                onClick={() => choose(q)}
                className="dropdown-item border-t border-line text-accent"
              >
                Load {q}
              </button>
            )}
            {filtered.length === 0 && !canLoadTyped && (
              <div className="px-3 py-3 text-[12.5px] text-fg-3">No symbols match.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
