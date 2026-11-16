import { ChevronLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface PanelProps {
  title: ReactNode;
  /** Right side of the header: a chip, a note or a link. */
  aside?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  /** Outlined in the accent, for the current plan. */
  current?: boolean;
  className?: string;
}

export function Panel({
  title,
  aside,
  children,
  footer,
  current = false,
  className = '',
}: PanelProps) {
  return (
    <section
      className={`min-w-0 overflow-hidden rounded-panel border bg-panel ${
        current ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line'
      } ${className}`}
    >
      <header className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-2.5 text-[12.5px]">
        <b className="font-semibold text-fg">{title}</b>
        {aside && <span className="text-fg-3">{aside}</span>}
      </header>
      {children}
      {footer && (
        <footer className="flex flex-wrap items-center justify-between gap-2.5 border-t border-line bg-sunk px-3.5 py-2.5 text-[12.5px]">
          {footer}
        </footer>
      )}
    </section>
  );
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0">
      <span className="text-fg-2">{label}</span>
      <span className="min-w-0 truncate text-right text-fg">{children}</span>
    </div>
  );
}

interface ListRowProps {
  lead?: ReactNode;
  title: ReactNode;
  sub?: ReactNode;
  end?: ReactNode;
}

export function ListRow({ lead, title, sub, end }: ListRowProps) {
  return (
    <div className="flex items-center gap-3 border-b border-line px-3.5 py-[9px] text-[12.5px] last:border-b-0">
      {lead && <span className="flex-none">{lead}</span>}
      <span className="min-w-0 flex-1">
        <b className="block font-semibold text-fg">{title}</b>
        {sub && <span className="block text-[11.5px] text-fg-3">{sub}</span>}
      </span>
      {end && <span className="flex flex-none items-center gap-2">{end}</span>}
    </div>
  );
}

export function Note({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 rounded-[8px] border border-line-strong bg-sunk px-3 py-2.5 text-[12.5px] text-fg-2">
      {icon && <span className="flex-none text-fg-2">{icon}</span>}
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

export function Meter({ fraction, label }: { fraction: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, fraction)) * 1000) / 10;
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className="my-1.5 h-1.5 overflow-hidden rounded-[3px] bg-sunk"
    >
      <i className="block h-full bg-accent-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Phone-only link back to the Account list. */
export function BackToAccount() {
  return (
    <Link
      to="/settings"
      className="mb-1 inline-flex items-center gap-0.5 text-[15px] text-accent md:hidden"
    >
      <ChevronLeft className="h-4 w-4" />
      Account
    </Link>
  );
}

/** A row in a phone list card. */
export function MobileRow({ children, end }: { children: ReactNode; end?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2.5 border-b border-line py-3 text-[15px] last:border-b-0">
      <span className="min-w-0">{children}</span>
      {end && <span className="flex flex-none items-center gap-1.5">{end}</span>}
    </div>
  );
}
