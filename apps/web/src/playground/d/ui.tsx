import {
  useMemo,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { Link } from 'react-router-dom';

import { useWidth } from '../../components/charts/useWidth';
import { ShapeLayer } from '../../marketing/components/ShapeLayer';
import { chartArt, SECTION_SHAPES, type SectionArtId } from '../../marketing/lib/sectionArt';
import { ACCOUNT, usd } from '../data';

import { ASSET_CLASSES } from './model';

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

const PANEL_STYLE: CSSProperties = {
  borderColor: 'color-mix(in srgb, rgb(var(--fg)) 22%, rgb(var(--line)))',
  boxShadow:
    '0 0 0 1px color-mix(in srgb, rgb(var(--fg)) 6%, transparent), 0 40px 120px -48px color-mix(in srgb, rgb(var(--fg)) 28%, transparent), 0 30px 60px -30px rgb(0 0 0 / 0.3)',
};

/** The crisp bordered sheet from the sign-in screen, lifted off the art behind it. */
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      style={PANEL_STYLE}
      className={`relative rounded-[14px] border bg-canvas before:pointer-events-none before:absolute before:inset-x-[10%] before:-top-px before:h-px before:bg-gradient-to-r before:from-transparent before:via-fg/60 before:to-transparent ${className}`}
    >
      {children}
    </section>
  );
}

const PAGE_MASK: CSSProperties = {
  WebkitMaskImage:
    'linear-gradient(to bottom, #000 40%, transparent 100%), radial-gradient(ellipse 44% 75% at 50% 40%, transparent 0, transparent 62%, #000 100%)',
  maskImage:
    'linear-gradient(to bottom, #000 40%, transparent 100%), radial-gradient(ellipse 44% 75% at 50% 40%, transparent 0, transparent 62%, #000 100%)',
  WebkitMaskComposite: 'source-in',
  maskComposite: 'intersect',
  color: 'rgb(var(--fg))',
};

const HERO_MASK: CSSProperties = {
  WebkitMaskImage:
    'linear-gradient(to bottom, transparent 0, #000 18%, #000 62%, transparent 100%)',
  maskImage: 'linear-gradient(to bottom, transparent 0, #000 18%, #000 62%, transparent 100%)',
  color: 'rgb(var(--fg))',
};

/** The faint candlestick chart behind the top of a page, with dotted levels and volume bars. */
export function Backdrop({
  shape = 'top',
  height = 520,
  hero = false,
}: {
  shape?: SectionArtId;
  height?: number;
  hero?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(1440);
  const groups = useMemo(
    () => chartArt(SECTION_SHAPES[shape], { width, top: height * 0.16, height: height * 0.56 }),
    [width, height, shape]
  );
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 top-0 overflow-hidden"
      style={{
        height,
        WebkitMaskImage: 'linear-gradient(to bottom, #000 55%, transparent)',
        maskImage: 'linear-gradient(to bottom, #000 55%, transparent)',
        background:
          'radial-gradient(50% 60% at 50% 30%, color-mix(in srgb, rgb(var(--fg)) 7%, transparent), transparent 75%)',
      }}
    >
      <div className="auth-art" style={hero ? HERO_MASK : PAGE_MASK}>
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
    <div className="grid min-w-0 content-start gap-1 py-3.5 [&+&]:border-l [&+&]:border-line [&+&]:pl-3 md:[&+&]:pl-5">
      <Label>{label}</Label>
      <div className="font-mono text-[19px] leading-tight tracking-[-0.03em] tabular-nums text-fg md:text-[24px]">
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

export function Foot({ items }: { items: string[] }) {
  return <p className="m-0 mt-10 text-[12px] text-fg-3">{items.join(' · ')}</p>;
}

/** A weight as a thin bar, with an optional tick at its target. */
export function WeightBar({
  value,
  target,
  max = 100,
}: {
  value: number;
  target?: number;
  max?: number;
}) {
  const at = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <span className="relative block h-[5px] w-full rounded-full bg-sunk">
      <i
        className="absolute inset-y-0 left-0 block rounded-full bg-fg"
        style={{ width: at(value) }}
      />
      {target !== undefined && (
        <i
          aria-hidden="true"
          className="absolute -top-[4px] block h-[13px] w-px bg-fg-3"
          style={{ left: at(target) }}
        />
      )}
    </span>
  );
}

const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.12, 0.92 - i * 0.12).toFixed(2)})`;

/** What the account holds by kind of fund: one stacked bar, then a row per class. */
export function ClassBar({ detail = false }: { detail?: boolean }) {
  const [hot, setHot] = useState<string | null>(null);
  const total = ACCOUNT.total;
  return (
    <div>
      <div className="flex h-8 w-full overflow-hidden rounded-[5px]">
        {ASSET_CLASSES.map((c, i) => (
          <span
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`block h-full border-r-2 border-canvas transition-opacity last:border-r-0 ${hot && hot !== c.name ? 'opacity-30' : ''}`}
            style={{
              width: `${(c.value / total) * 100}%`,
              background:
                c.name === 'Cash'
                  ? 'repeating-linear-gradient(135deg, rgb(var(--fg) / 0.35) 0 1px, transparent 1px 5px)'
                  : shade(i),
            }}
          />
        ))}
      </div>
      <div className="mt-4 border-t border-line">
        {ASSET_CLASSES.map((c, i) => (
          <div
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`grid grid-cols-[12px_minmax(0,1fr)_60px_110px] items-center gap-4 border-b border-line py-2.5 text-[13px] transition-colors md:grid-cols-[12px_minmax(0,1fr)_minmax(0,1fr)_64px_120px_90px] ${hot === c.name ? 'bg-panel/70' : ''}`}
          >
            <i
              className={`h-2.5 w-2.5 rounded-[2px] ${c.name === 'Cash' ? 'border border-fg-3' : ''}`}
              style={c.name === 'Cash' ? undefined : { background: shade(i) }}
            />
            <span className="truncate text-fg">{c.name}</span>
            <span className="hidden truncate font-mono text-[11.5px] text-fg-3 md:block">
              {c.symbols.join(' ') || (detail ? 'Stopped session and unused cash' : '')}
            </span>
            <span className="text-right font-mono tabular-nums text-fg-2">
              {((c.value / total) * 100).toFixed(1)}%
            </span>
            <span className="text-right font-mono tabular-nums text-fg">{usd(c.value)}</span>
            <Delta v={c.today} className="hidden text-right text-[12.5px] md:block">
              {c.today === 0 ? '' : `${c.today > 0 ? '+' : '−'}$${Math.abs(c.today).toFixed(2)}`}
            </Delta>
          </div>
        ))}
      </div>
    </div>
  );
}
