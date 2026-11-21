import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link, type To } from 'react-router-dom';

export function Label({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`text-[11.5px] font-medium text-fg-3 ${className}`}>{children}</span>;
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`font-mono text-[10.5px] font-medium uppercase leading-none tracking-[0.08em] ${className}`}
    >
      {children}
    </span>
  );
}

type Variant = 'primary' | 'secondary' | 'quiet';
const VARIANT: Record<Variant, string> = {
  primary: 'bg-fg text-canvas hover:bg-fg/90',
  secondary: 'border border-line-strong text-fg hover:border-fg-3 hover:bg-sunk',
  quiet: 'text-fg-2 hover:bg-sunk hover:text-fg',
};

const buttonClass = (variant: Variant, size: 'sm' | 'md') =>
  `inline-flex flex-none items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-medium transition-colors ${
    size === 'sm' ? 'h-7 px-3 text-[12.5px]' : 'h-9 px-4 text-[13px]'
  } ${VARIANT[variant]}`;

export function Button({
  variant = 'secondary',
  size = 'sm',
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' }) {
  return (
    <button type="button" className={`${buttonClass(variant, size)} ${className}`} {...rest} />
  );
}

export function LinkButton({
  to,
  variant = 'secondary',
  size = 'sm',
  children,
}: {
  to: string;
  variant?: Variant;
  size?: 'sm' | 'md';
  children: ReactNode;
}) {
  return (
    <Link to={to} className={buttonClass(variant, size)}>
      {children}
    </Link>
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
  if (!mode) return <span className="font-mono text-[11px] text-fg-3">·</span>;
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

/** One figure in a three-up strip: grey label, big mono numeral, a small SPY comparison. */
export function Figure({
  label,
  children,
  sub,
}: {
  label: string;
  children: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="grid min-w-0 content-start gap-0.5 py-2.5 [&+&]:border-l [&+&]:border-line [&+&]:pl-3.5">
      <span className="text-[11px] font-medium text-fg-3">{label}</span>
      <div className="font-mono text-[19px] leading-tight tracking-[-0.03em] tabular-nums text-fg md:text-[22px]">
        {children}
      </div>
      {sub !== undefined && (
        <span className="truncate font-mono text-[11.5px] tabular-nums text-fg-3">{sub}</span>
      )}
    </div>
  );
}

export function Figures({ children, cols = 3 }: { children: ReactNode; cols?: 3 | 4 | 5 }) {
  const grid = {
    3: 'grid-cols-3',
    4: 'grid-cols-2 md:grid-cols-4',
    5: 'grid-cols-3 md:grid-cols-5',
  }[cols];
  return <div className={`grid border-y border-line ${grid}`}>{children}</div>;
}

/** A small line, optionally over a dashed benchmark, with a soft fill. */
export function Spark({
  values,
  bench,
  width = 112,
  height = 28,
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
      <path
        d={`${path(values)} L${width},${height} L0,${height} Z`}
        fill="rgb(var(--fg))"
        opacity={0.06}
      />
      {bench && (
        <path
          d={path(bench)}
          fill="none"
          stroke="rgb(var(--fg-3))"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
      )}
      <path d={path(values)} fill="none" stroke={stroke} strokeWidth={1.4} strokeLinejoin="round" />
    </svg>
  );
}

/** A segmented pill control, used for ranges and filters. */
export function Segmented<T extends string>({
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
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex items-center rounded-full border border-line p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="tab"
          aria-selected={o.key === value}
          onClick={() => onChange(o.key)}
          className={`h-6 rounded-full px-2.5 font-mono text-[11px] tabular-nums transition-colors ${
            o.key === value ? 'bg-fg text-canvas' : 'text-fg-3 hover:text-fg'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Head of a ledger section: a title, a grey meta line and controls on the right. */
export function SectionHead({
  title,
  meta,
  right,
}: {
  title: string;
  meta?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 pb-3">
      <div className="min-w-0">
        <h2 className="m-0 text-[17px] font-semibold tracking-[-0.015em] text-fg">{title}</h2>
        {meta && <div className="mt-0.5 text-[12.5px] text-fg-3">{meta}</div>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

export function Chevron({ open }: { open: boolean }) {
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

/** The crisp bordered sheet from the sign-in screen, lifted off the art on the stage. */
export function StageCard({ children }: { children: ReactNode }) {
  return (
    <section className="auth-card relative w-full rounded-[14px] border bg-canvas p-5 md:p-7">
      {children}
    </section>
  );
}

/** Head of a stage panel, set like the example backtest: eyebrow, title, one grey line. */
export function PanelHead({
  eyebrow,
  title,
  meta,
  right,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <span className="text-[11px] font-medium text-fg-3">{eyebrow}</span>
        <h2 className="m-0 mt-1 text-[20px] font-semibold leading-tight tracking-[-0.015em] text-fg">
          {title}
        </h2>
        {meta && <div className="mt-[3px] text-[12px] text-fg-3">{meta}</div>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

/** The footnote line under a stage panel, with actions on the right. */
export function PanelFoot({
  note,
  children,
  flush = false,
}: {
  note: ReactNode;
  children?: ReactNode;
  /** Set when a full-bleed rule already sits right above the foot. */
  flush?: boolean;
}) {
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 pt-4 ${flush ? '' : 'mt-5 border-t border-line'}`}
    >
      <p className="m-0 max-w-[420px] text-[11.5px] text-fg-3">{note}</p>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

/** Head of the left column, set like the sign-in form's header. */
export function LeftHead({
  eyebrow,
  title,
  sub,
  right,
}: {
  eyebrow?: ReactNode;
  title: string;
  sub?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <header className="flex items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <span className="text-[11.5px] font-medium text-fg-3">{eyebrow}</span>}
        <h1 className="m-0 mt-0.5 text-[22px] font-semibold leading-tight tracking-[-0.02em] text-fg">
          {title}
        </h1>
        {sub && <p className="mb-0 mt-[5px] text-[13px] text-fg-2">{sub}</p>}
      </div>
      {right}
    </header>
  );
}

/** A small grey heading over a list in the left column. */
export function ListLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-1 mt-7 flex items-center justify-between border-b border-line pb-2 text-[11.5px] font-medium text-fg-3">
      <span>{children}</span>
      {right}
    </div>
  );
}

/** One selectable row in the left column; the selected row's object is on the stage. */
export function PickRow({
  to,
  on,
  title,
  sub,
  right,
  muted = false,
}: {
  to: To;
  on: boolean;
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  muted?: boolean;
}) {
  return (
    <Link
      to={to}
      replace
      aria-current={on ? 'true' : undefined}
      className={`relative -mx-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[8px] px-3 py-2.5 transition-colors ${
        on ? 'bg-sunk' : 'hover:bg-sunk/60'
      } ${muted && !on ? 'opacity-60' : ''}`}
    >
      <span className="min-w-0">
        <span className={`block truncate text-[13.5px] ${on ? 'font-medium text-fg' : 'text-fg'}`}>
          {title}
        </span>
        {sub && <span className="mt-0.5 block truncate text-[12px] text-fg-3">{sub}</span>}
      </span>
      {right && <span className="flex items-center gap-2.5">{right}</span>}
    </Link>
  );
}
