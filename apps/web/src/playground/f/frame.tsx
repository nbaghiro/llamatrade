import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { LogoMark } from '../../components/common/Logo';
import type { SectionArtId } from '../../marketing/lib/sectionArt';
import { MARKET } from '../data';

import { PAGES } from './commands';
import { useCopilot } from './copilotContext';
import { to } from './model';
import { Band, Kbd, Mono } from './ui';

export const WRAP = 'mx-auto max-w-[1320px] px-4 md:px-6';

export function TopBar() {
  const { pathname } = useLocation();
  const { openBar } = useCopilot();
  const isOn = (p: string) =>
    p === '' ? pathname === to() || pathname === to('/') : pathname.startsWith(to(p));
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/95 backdrop-blur-[2px]">
      <div className={`${WRAP} flex h-11 items-center gap-4`}>
        <NavLink to={to()} className="flex flex-none items-center gap-2.5 text-fg">
          <LogoMark size={24} bold className="-my-2" />
          <span className="hidden font-mono text-[11px] font-semibold uppercase tracking-[0.16em] xl:inline">
            LlamaTrade
          </span>
        </NavLink>
        <nav className="-mx-1 flex min-w-0 items-center overflow-x-auto">
          {PAGES.map((p) => (
            <NavLink
              key={p.label}
              to={to(p.path)}
              className={`group inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-[5px] px-2.5 text-[12.5px] transition-colors ${
                isOn(p.path) ? 'bg-sunk font-medium text-fg' : 'text-fg-3 hover:text-fg'
              }`}
            >
              <span className="hidden font-mono text-[10px] text-fg-3 lg:inline">{p.key}</span>
              {p.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => openBar()}
          className="ml-auto hidden h-7 min-w-0 flex-1 items-center gap-2 rounded-[6px] border border-line px-2.5 text-left font-mono text-[11.5px] text-fg-3 transition-colors hover:border-line-strong hover:text-fg-2 md:flex md:max-w-[340px]"
        >
          <span aria-hidden="true">›</span>
          <span className="min-w-0 flex-1 truncate">Ask, jump or run a command</span>
          <Kbd>⌘K</Kbd>
        </button>
        <div className="hidden flex-none items-center gap-4 font-mono text-[11px] tabular-nums lg:flex">
          <span className="inline-flex items-center gap-1.5 text-fg-3">
            <i className="h-1.5 w-1.5 rounded-full bg-gain" aria-hidden="true" />
            Open to 16:00
          </span>
          {MARKET.quotes.map((q) => (
            <span key={q.symbol} className="text-fg-2">
              {q.symbol} {q.price.toFixed(2)}{' '}
              <span className={q.change < 0 ? 'text-loss' : 'text-gain'}>
                {q.change < 0 ? '−' : '+'}
                {Math.abs(q.change * 100).toFixed(2)}%
              </span>
            </span>
          ))}
        </div>
        <button
          type="button"
          onClick={() => openBar()}
          aria-label="Open command bar"
          className="grid h-7 w-7 flex-none place-items-center rounded-[6px] border border-line font-mono text-[12px] text-fg-2 md:hidden"
        >
          ›
        </button>
        <span className="grid h-7 w-7 flex-none place-items-center rounded-full border border-line-strong font-mono text-[10.5px] font-medium text-fg-2">
          NB
        </span>
      </div>
    </header>
  );
}

/** A page: the candle band behind a compact head, then a 12-column grid of blocks. */
export function Page({
  head,
  children,
  art = 'top',
}: {
  head: ReactNode;
  children: ReactNode;
  art?: SectionArtId;
}) {
  return (
    <div className="relative">
      <Band shape={art} />
      <div className={`relative ${WRAP} pb-20 pt-5`}>
        {head}
        <div className="mt-4 grid grid-cols-12 gap-3">{children}</div>
      </div>
    </div>
  );
}

export function Head({
  crumb,
  title,
  meta,
  right,
  figure,
}: {
  crumb: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  right?: ReactNode;
  figure?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <Mono className="text-fg-3">{crumb}</Mono>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="m-0 text-[22px] font-semibold leading-none tracking-[-0.02em] text-fg">
            {title}
          </h1>
          {figure}
        </div>
        {meta && <div className="mt-2 font-mono text-[11.5px] text-fg-3">{meta}</div>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

/** A thin status line at the bottom: the keys this page answers to. */
export function StatusBar() {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 hidden border-t border-line bg-canvas/95 md:block">
      <div className="mx-auto flex h-7 max-w-[1320px] items-center justify-end gap-4 px-6 font-mono text-[10.5px] text-fg-3">
        <span className="inline-flex items-center gap-1.5">
          <Kbd>j</Kbd>
          <Kbd>k</Kbd> move
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Kbd>↵</Kbd> open
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Kbd>e</Kbd> edit
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Kbd>/</Kbd> ask or jump
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Kbd>1</Kbd>–<Kbd>5</Kbd> pages
        </span>
        <span className="text-fg-3/80">
          Prices Nov 20, 12:04 ET · history before Nov 12 is sample
        </span>
      </div>
    </div>
  );
}
