import { Plus } from 'lucide-react';
import { useRef, useState, type FormEvent, type PointerEvent as ReactPointerEvent } from 'react';

import { isValidSymbol, normaliseSymbol } from '../../../lib/outline';
import { HOLDING_FILLS } from '../outline/holdingFills';

import { dragEdge, type WeightRow } from './weightMath';

export function WeightBar({
  rows,
  weights,
  onLive,
  onCommit,
}: {
  rows: readonly WeightRow[];
  weights: readonly number[];
  onLive: (w: number[] | null) => void;
  onCommit: (w: number[]) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const drag = useRef<{ edge: number; x: number; base: number[]; last: number[] } | null>(null);
  const [active, setActive] = useState<number | null>(null);

  const down = (edge: number) => (e: ReactPointerEvent<HTMLButtonElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { edge, x: e.clientX, base: [...weights], last: [...weights] };
    setActive(edge);
  };
  const move = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    const width = bar.current?.clientWidth ?? 0;
    if (!d || width <= 0) return;
    const delta = Math.round(((e.clientX - d.x) / width) * 1000) / 10;
    d.last = dragEdge(d.base, d.edge, delta);
    onLive(d.last);
  };
  const up = () => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setActive(null);
    onLive(null);
    onCommit(d.last);
  };
  const nudge = (edge: number, delta: number) => onCommit(dragEdge(weights, edge, delta));

  let acc = 0;
  return (
    <div className="relative pt-8">
      <div ref={bar} className="relative flex h-16 gap-0.5">
        {rows.map((r, i) => {
          const w = weights[i] ?? 0;
          const fill = HOLDING_FILLS[i % HOLDING_FILLS.length];
          return (
            <div
              key={r.id}
              className={`relative min-w-0 overflow-hidden rounded-[4px] px-3 py-2 ${w <= 0 ? 'border border-dashed border-line-strong' : ''}`}
              style={{
                width: w > 0 ? `${w}%` : '64px',
                flex: w > 0 ? undefined : 'none',
                background: w > 0 ? fill : undefined,
              }}
            >
              <span
                className={`inline-grid max-w-full rounded-[3px] px-1 ${w > 0 ? 'bg-canvas/85 text-fg' : 'text-fg-3'}`}
              >
                <span className="block truncate font-mono text-[11.5px]">{r.label}</span>
                <span className="block font-mono text-[16px]">{Math.round(w * 10) / 10}%</span>
              </span>
            </div>
          );
        })}
        {rows.slice(0, -1).map((r, i) => {
          acc += weights[i] ?? 0;
          const next = rows[i + 1];
          return (
            <button
              key={`edge-${r.id}`}
              type="button"
              aria-label={`Move weight between ${r.label} and ${next.label}`}
              onPointerDown={down(i)}
              onPointerMove={move}
              onPointerUp={up}
              onKeyDown={(e) => {
                if (e.key === 'ArrowLeft') nudge(i, -1);
                if (e.key === 'ArrowRight') nudge(i, 1);
              }}
              className="absolute top-1/2 z-10 h-[72px] w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize touch-none rounded-[6px] border border-fg bg-panel focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
              style={{ left: `${acc}%` }}
            >
              {active === i && (
                <span className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-[4px] bg-fg px-2 py-1 font-mono text-[11px] text-canvas">
                  {r.label} {Math.round((weights[i] ?? 0) * 10) / 10} · {next.label}{' '}
                  {Math.round((weights[i + 1] ?? 0) * 10) / 10}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function AddSymbol({ onAdd }: { onAdd: (symbol: string) => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!isValidSymbol(value)) {
      setError('Enter a ticker, for example VTI.');
      return;
    }
    onAdd(normaliseSymbol(value));
    setValue('');
    setOpen(false);
  };
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="btn btn-ghost btn-sm text-fg">
        <Plus className="h-4 w-4" />
        Add a symbol
      </button>
    );
  }
  return (
    <form onSubmit={submit} className="flex items-start gap-2">
      <span className="grid gap-1">
        <input
          autoFocus
          aria-label="Ticker to add"
          value={value}
          placeholder="IEF"
          onChange={(e) => {
            setError(null);
            setValue(e.target.value.toUpperCase());
          }}
          className={`input h-8 w-[110px] font-mono ${error ? 'input-error' : ''}`}
        />
        {error && <span className="text-[11.5px] text-risk">{error}</span>}
      </span>
      <button type="submit" className="btn btn-primary btn-sm">
        Add
      </button>
      <button type="button" onClick={() => setOpen(false)} className="btn btn-ghost btn-sm">
        Cancel
      </button>
    </form>
  );
}
