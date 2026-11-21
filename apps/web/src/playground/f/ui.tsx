import { useMemo, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useWidth } from '../../components/charts/useWidth';
import { ShapeLayer } from '../../marketing/components/ShapeLayer';
import { chartArt, SECTION_SHAPES, type SectionArtId } from '../../marketing/lib/sectionArt';

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`font-mono text-[10.5px] font-medium uppercase leading-none tracking-[0.08em] ${className}`}
    >
      {children}
    </span>
  );
}

export function Kbd({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={`inline-grid h-[18px] min-w-[18px] place-items-center rounded-[4px] border border-line px-1 font-mono text-[10.5px] font-normal leading-none text-fg-3 ${className}`}
    >
      {children}
    </kbd>
  );
}

type Variant = 'primary' | 'secondary' | 'quiet';
const VARIANT: Record<Variant, string> = {
  primary: 'bg-fg text-canvas hover:bg-fg/90',
  secondary: 'border border-line-strong text-fg hover:border-fg-3 hover:bg-sunk',
  quiet: 'text-fg-2 hover:bg-sunk hover:text-fg',
};

const buttonClass = (variant: Variant) =>
  `inline-flex h-7 flex-none items-center justify-center gap-2 whitespace-nowrap rounded-[6px] px-2.5 text-[12.5px] font-medium transition-colors ${VARIANT[variant]}`;

function KeyHint({ k, variant }: { k?: string; variant: Variant }) {
  if (!k) return null;
  return (
    <span
      className={`font-mono text-[10.5px] font-normal ${variant === 'primary' ? 'text-canvas/60' : 'text-fg-3'}`}
    >
      {k}
    </span>
  );
}

export function Button({
  variant = 'secondary',
  k,
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; k?: string }) {
  return (
    <button type="button" className={`${buttonClass(variant)} ${className}`} {...rest}>
      {children}
      <KeyHint k={k} variant={variant} />
    </button>
  );
}

export function LinkButton({
  to,
  variant = 'secondary',
  k,
  children,
}: {
  to: string;
  variant?: Variant;
  k?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={buttonClass(variant)}>
      {children}
      <KeyHint k={k} variant={variant} />
    </Link>
  );
}

/** A bordered block with a 32px mono head: the one container every page is built from. */
export function Block({
  title,
  meta,
  right,
  children,
  className = '',
  bodyClass = '',
}: {
  title: ReactNode;
  meta?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section
      className={`flex min-w-0 flex-col overflow-hidden rounded-[8px] border border-line bg-canvas ${className}`}
    >
      <header className="flex h-8 items-center gap-3 border-b border-line bg-panel/60 px-3">
        <Mono className="flex-none text-fg-2">{title}</Mono>
        {meta && (
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-fg-3">{meta}</span>
        )}
        {!meta && <span className="flex-1" />}
        {right && <div className="flex flex-none items-center gap-2">{right}</div>}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClass}`}>{children}</div>
    </section>
  );
}

/** The sign-in screen's faint candle chart, kept to a thin band behind the page head. */
export function Band({ shape = 'top', height = 132 }: { shape?: SectionArtId; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>(1440);
  const groups = useMemo(
    () => chartArt(SECTION_SHAPES[shape], { width, top: height * 0.08, height: height * 0.8 }),
    [width, height, shape]
  );
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 top-0 overflow-hidden opacity-50"
      style={{ height }}
    >
      <div
        className="auth-art"
        style={{
          WebkitMaskImage: 'linear-gradient(to bottom, #000 30%, transparent 100%)',
          maskImage: 'linear-gradient(to bottom, #000 30%, transparent 100%)',
          color: 'rgb(var(--fg))',
        }}
      >
        <ShapeLayer width={width} height={height} groups={groups} inheritColor />
      </div>
    </div>
  );
}

export function Delta({
  v,
  children,
  className = '',
}: {
  v: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`font-mono tabular-nums ${v > 0 ? 'text-gain' : v < 0 ? 'text-loss' : 'text-fg-3'} ${className}`}
    >
      {children}
    </span>
  );
}

export function ModeTag({ mode }: { mode?: 'live' | 'paper' }) {
  if (!mode) return <Mono className="text-fg-3">off</Mono>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <i
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${mode === 'live' ? 'bg-gain' : 'border border-fg-3'}`}
      />
      <Mono className={mode === 'live' ? 'text-fg' : 'text-fg-2'}>{mode}</Mono>
    </span>
  );
}

/** A row of figures: mono label, mono numeral, a small comparison. Cells share hairlines. */
export function Stats({
  items,
  className = '',
}: {
  items: { label: string; value: ReactNode; sub?: ReactNode }[];
  className?: string;
}) {
  const cols: Record<number, string> = {
    3: 'grid-cols-3',
    4: 'grid-cols-2 md:grid-cols-4',
    5: 'grid-cols-3 md:grid-cols-5',
    6: 'grid-cols-3 md:grid-cols-6',
  };
  return (
    <div className={`grid ${cols[items.length] ?? 'grid-cols-3'} ${className}`}>
      {items.map((it) => (
        <div
          key={it.label}
          className="grid min-w-0 content-start gap-1 border-line px-3 py-2.5 [&:not(:first-child)]:border-l"
        >
          <Mono className="truncate text-fg-3">{it.label}</Mono>
          <div className="truncate font-mono text-[17px] leading-tight tracking-[-0.02em] tabular-nums text-fg">
            {it.value}
          </div>
          {it.sub !== undefined && (
            <span className="truncate font-mono text-[11px] tabular-nums text-fg-3">{it.sub}</span>
          )}
        </div>
      ))}
    </div>
  );
}

/** A small line, optionally over a dashed benchmark. */
export function Spark({
  values,
  bench,
  width = 96,
  height = 20,
  toneBy = true,
}: {
  values: readonly number[];
  bench?: readonly number[];
  width?: number;
  height?: number;
  toneBy?: boolean;
}) {
  if (values.length < 2) return <svg width={width} height={height} aria-hidden="true" />;
  const all = [...values, ...(bench ?? [])];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const span = hi - lo || 1;
  const x = (i: number, n: number) => (i / (n - 1)) * width;
  const y = (v: number) => 2 + (1 - (v - lo) / span) * (height - 4);
  const path = (s: readonly number[]) =>
    s.map((v, i) => `${i ? 'L' : 'M'}${x(i, s.length).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const up = values[values.length - 1] >= values[0];
  const stroke = toneBy ? (up ? 'rgb(var(--gain))' : 'rgb(var(--loss))') : 'rgb(var(--fg))';
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {bench && (
        <path
          d={path(bench)}
          fill="none"
          stroke="rgb(var(--fg-3))"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
      )}
      <path d={path(values)} fill="none" stroke={stroke} strokeWidth={1.3} strokeLinejoin="round" />
    </svg>
  );
}

/** Mono segmented control, used for ranges and filters, with an optional key per option. */
export function Seg<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: readonly { key: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex items-center gap-px">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="tab"
          aria-selected={o.key === value}
          onClick={() => onChange(o.key)}
          className={`h-[22px] rounded-[4px] px-2 font-mono text-[11px] tabular-nums transition-colors ${
            o.key === value ? 'bg-fg text-canvas' : 'text-fg-3 hover:bg-sunk hover:text-fg'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Caret({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 10 10"
      aria-hidden="true"
      className={`h-2.5 w-2.5 transition-transform ${open ? '' : '-rotate-90'}`}
    >
      <path
        d="M2 3.5l3 3 3-3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Column head of a ledger: mono labels on a 32px row. */
export function TableHead({ cols, children }: { cols: string; children: ReactNode }) {
  return (
    <div
      className={`grid ${cols} h-8 items-center gap-3 border-b border-line px-3 font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-fg-3`}
    >
      {children}
    </div>
  );
}
