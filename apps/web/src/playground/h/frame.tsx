import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { LogoMark } from '../../components/common/Logo';
import { ACCOUNT, MARKET, usd } from '../data';

import { AskLine } from './ask';
import { pts2 } from './model';
import { DATELINE, TIME, todayPct } from './paper';
import { SERIF, WRAP } from './style';
import { Backdrop, Delta, Head, Mono } from './ui';

const NAV = [
  { to: '/h', label: 'Today' },
  { to: '/h/strategies', label: 'Strategies' },
  { to: '/h/backtests', label: 'Backtests' },
  { to: '/h/sessions', label: 'Sessions' },
  { to: '/h/portfolio', label: 'Portfolio' },
];

/** The nameplate: dateline and market, the paper's name, the account, then the sections. */
export function Masthead() {
  const { pathname } = useLocation();
  const isOn = (to: string) =>
    to === '/h' ? pathname === '/h' || pathname === '/h/' : pathname.startsWith(to);
  return (
    <header className="relative">
      <Backdrop shape="top" height={260} />
      <div className={`relative ${WRAP}`}>
        <div className="flex h-9 items-center justify-between gap-4 border-b border-line font-mono text-[11px] tabular-nums text-fg-3">
          <span className="truncate">
            {DATELINE} · {TIME}
          </span>
          <span className="hidden items-center gap-4 sm:flex">
            <span className="inline-flex items-center gap-1.5">
              <i className="h-1.5 w-1.5 rounded-full bg-gain" aria-hidden="true" />
              {MARKET.status}
            </span>
            {MARKET.quotes.map((q) => (
              <span key={q.symbol} className="text-fg-2">
                {q.symbol} {q.price.toFixed(2)} <Delta v={q.change}>{pts2(q.change * 100)}</Delta>
              </span>
            ))}
          </span>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 py-5 md:py-7">
          <div className="hidden min-w-0 text-[12px] leading-[1.5] text-fg-3 md:block">
            <div>Live {usd(ACCOUNT.live)}</div>
            <div>Paper {usd(ACCOUNT.paper)}</div>
          </div>
          <NavLink to="/h" className="col-start-2 flex items-center gap-3 text-fg">
            <LogoMark size={36} bold className="-my-2" />
            <span
              style={SERIF}
              className="text-[34px] font-medium leading-none tracking-[-0.03em] md:text-[46px]"
            >
              LlamaTrade
            </span>
          </NavLink>
          <div className="col-start-3 flex items-center justify-end gap-4">
            <div className="hidden text-right md:block">
              <div className="font-mono text-[15px] tabular-nums text-fg">{usd(ACCOUNT.total)}</div>
              <Delta v={ACCOUNT.today} className="text-[11.5px]">
                {pts2(todayPct * 100)} today
              </Delta>
            </div>
            <span className="grid h-8 w-8 flex-none place-items-center rounded-full border border-line-strong text-[11px] font-medium text-fg-2">
              NB
            </span>
          </div>
        </div>
        <nav className="border-y border-fg">
          <div className="-mx-2 flex items-center justify-start gap-1 overflow-x-auto py-1 md:justify-center md:gap-3">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={`whitespace-nowrap px-2 py-1.5 text-[13px] transition-colors ${
                  isOn(n.to)
                    ? 'font-medium text-fg underline decoration-fg decoration-[1.5px] underline-offset-[9px]'
                    : 'text-fg-3 hover:text-fg'
                }`}
              >
                {n.label}
              </NavLink>
            ))}
          </div>
        </nav>
        <div className="mt-[3px] border-t border-line" />
      </div>
    </header>
  );
}

/** One section of the paper: the Ask line, then the page. */
export function Page({
  children,
  ask,
}: {
  children: ReactNode;
  ask: { context?: string; placeholder?: string; suggestions?: string[] };
}) {
  return (
    <main className={`${WRAP} pb-28 pt-5`}>
      <AskLine {...ask} />
      <div className="mt-10 md:mt-12">{children}</div>
    </main>
  );
}

/** A section's lead: a kicker line, a serif headline written from the data, one short deck line. */
export function Lead({
  kicker,
  headline,
  deck,
  right,
  size = 48,
}: {
  kicker: ReactNode;
  headline: ReactNode;
  deck?: ReactNode;
  right?: ReactNode;
  size?: number;
}) {
  return (
    <div className="mb-9 flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
      <div className="min-w-0 max-w-[900px]">
        <Mono className="text-fg-3">{kicker}</Mono>
        <div className="mt-3">
          <Head as="h1" size={size}>
            <span className="block text-[0.62em] md:text-[1em]">{headline}</span>
          </Head>
        </div>
        {deck && <p className="m-0 mt-3 text-[15px] text-fg-2">{deck}</p>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}

export function Dateline({ items }: { items: string[] }) {
  return (
    <p className="m-0 mt-14 border-t border-line pt-3 text-[11.5px] text-fg-3">
      {items.join(' · ')}
    </p>
  );
}
