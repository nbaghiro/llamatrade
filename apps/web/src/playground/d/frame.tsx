import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { LogoMark } from '../../components/common/Logo';
import type { SectionArtId } from '../../marketing/lib/sectionArt';
import { MARKET } from '../data';

import { Brief, Composer } from './ask';
import { Backdrop } from './ui';

const NAV = [
  { to: '/d', label: 'Today' },
  { to: '/d/strategies', label: 'Strategies' },
  { to: '/d/backtests', label: 'Backtests' },
  { to: '/d/sessions', label: 'Sessions' },
  { to: '/d/portfolio', label: 'Portfolio' },
];

export function TopBar() {
  const spy = MARKET.quotes[0];
  const { pathname } = useLocation();
  const isOn = (to: string) =>
    to === '/d' ? pathname === '/d' || pathname === '/d/' : pathname.startsWith(to);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="mx-auto flex h-14 max-w-[1120px] items-center gap-6 px-4 md:px-10">
        <NavLink to="/d" className="flex flex-none items-center gap-3 text-fg">
          <LogoMark size={30} bold className="-my-2" />
          <span className="hidden text-[11.5px] font-semibold uppercase tracking-[0.16em] lg:inline">
            LlamaTrade
          </span>
        </NavLink>
        <nav className="-mx-1 flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={`whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] transition-colors ${
                isOn(n.to) ? 'bg-sunk font-medium text-fg' : 'text-fg-3 hover:text-fg'
              }`}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden flex-none items-center gap-4 font-mono text-[11.5px] tabular-nums md:flex">
          <span className="inline-flex items-center gap-1.5 text-fg-3">
            <i className="h-1.5 w-1.5 rounded-full bg-gain" aria-hidden="true" />
            {MARKET.status}
          </span>
          <span className="text-fg-2">
            SPY {spy.price.toFixed(2)}{' '}
            <span className="text-loss">−{Math.abs(spy.change * 100).toFixed(2)}%</span>
          </span>
        </div>
        <span className="grid h-7 w-7 flex-none place-items-center rounded-full border border-line-strong text-[11px] font-medium text-fg-2">
          NB
        </span>
      </div>
    </header>
  );
}

/** One page: the art behind its top, the Ask line with its answers inline, then the page itself. */
export function Page({
  children,
  context,
  placeholder,
  art = 'top',
}: {
  children: ReactNode;
  context?: string;
  placeholder?: string;
  art?: SectionArtId;
}) {
  return (
    <div className="relative">
      <Backdrop shape={art} height={320} />
      <div className="relative mx-auto max-w-[1120px] px-4 pb-32 pt-8 md:px-10">
        <Composer context={context} placeholder={placeholder} />
        <Brief context={context} gutter={false} />
        <div className="mt-14">{children}</div>
      </div>
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  meta,
  right,
}: {
  eyebrow: ReactNode;
  title: string;
  meta?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <span className="font-mono text-[11px] text-fg-3">{eyebrow}</span>
        <h1 className="m-0 mt-2 text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-fg md:text-[36px]">
          {title}
        </h1>
        {meta && <div className="mt-2 max-w-[640px] text-[13.5px] text-fg-3">{meta}</div>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

/** A section of a page: title and meta over a hairline, no box. */
export function Block({
  title,
  meta,
  right,
  children,
  className = 'mt-20',
}: {
  title: string;
  meta?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={className}>
      <div className="flex flex-wrap items-end justify-between gap-3 pb-4">
        <div className="min-w-0">
          <h2 className="m-0 text-[19px] font-semibold tracking-[-0.02em] text-fg">{title}</h2>
          {meta && <div className="mt-1 text-[12.5px] text-fg-3">{meta}</div>}
        </div>
        {right && <div className="flex items-center gap-2">{right}</div>}
      </div>
      {children}
    </section>
  );
}
