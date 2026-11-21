import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { LogoMark } from '../../components/common/Logo';
import type { SectionArtId } from '../../marketing/lib/sectionArt';
import { MARKET } from '../data';

import { AskLine } from './ask';
import { Backdrop } from './ui';

const NAV = [
  { to: '/c', label: 'Today' },
  { to: '/c/strategies', label: 'Strategies' },
  { to: '/c/backtests', label: 'Backtests' },
  { to: '/c/sessions', label: 'Sessions' },
  { to: '/c/portfolio', label: 'Portfolio' },
];

export function TopBar() {
  const spy = MARKET.quotes[0];
  const { pathname } = useLocation();
  const isOn = (to: string) =>
    to === '/c' ? pathname === '/c' || pathname === '/c/' : pathname.startsWith(to);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="mx-auto flex h-14 max-w-[1120px] items-center gap-6 px-4 md:px-10">
        <NavLink to="/c" className="flex flex-none items-center gap-3 text-fg">
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

/** One page: the art behind its top, the Ask line, then the page's own head and ledger. */
export function Page({
  children,
  ask,
  art = 'top',
}: {
  children: ReactNode;
  ask?: { context?: string; placeholder?: string } | false;
  art?: SectionArtId;
}) {
  return (
    <div className="relative">
      <Backdrop shape={art} />
      <div className="relative mx-auto max-w-[1120px] px-4 pb-28 pt-7 md:px-10">
        {ask !== false && (
          <div className="mb-9">
            <AskLine context={ask?.context} placeholder={ask?.placeholder} />
          </div>
        )}
        {children}
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
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <span className="text-[11.5px] font-medium text-fg-3">{eyebrow}</span>
        <h1 className="m-0 mt-1 text-[28px] font-semibold leading-tight tracking-[-0.025em] text-fg">
          {title}
        </h1>
        {meta && <div className="mt-1 text-[13px] text-fg-3">{meta}</div>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}
