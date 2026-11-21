import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { AuthArt } from '../../components/auth/AuthArt';
import { LogoMark } from '../../components/common/Logo';
import { MARKET } from '../data';

const NAV = [
  { to: '/i', label: 'Today' },
  { to: '/i/strategies', label: 'Strategies' },
  { to: '/i/backtests', label: 'Backtests' },
  { to: '/i/sessions', label: 'Sessions' },
  { to: '/i/portfolio', label: 'Portfolio' },
];

const MOTION = `
@keyframes i-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes i-out { from { opacity: 1; } to { opacity: 0; } }
.i-in { animation: i-in 0.42s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
.i-out { animation: i-out 0.18s linear both; pointer-events: none; }
.i-art { transition: transform 1.1s cubic-bezier(0.2, 0.7, 0.2, 1); }
@media (prefers-reduced-motion: reduce) { .i-in, .i-out { animation: none; } .i-art { transition: none; } }
`;

function Avatar() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Account menu"
        className="grid h-7 w-7 place-items-center rounded-full border border-line-strong text-[11px] font-medium text-fg-2 hover:text-fg"
      >
        NB
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-50 grid w-44 animate-rise gap-0.5 rounded-[10px] border border-line-strong bg-canvas p-1 text-[13px] shadow-lg">
          <span className="px-2.5 py-1.5 text-[12px] text-fg-3">naib@llamatrade.dev</span>
          <button
            type="button"
            className="rounded-[6px] px-2.5 py-1.5 text-left text-fg hover:bg-sunk"
          >
            Settings
          </button>
          <button
            type="button"
            className="rounded-[6px] px-2.5 py-1.5 text-left text-fg hover:bg-sunk"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function TopBar() {
  const spy = MARKET.quotes[0];
  const { pathname } = useLocation();
  const isOn = (to: string) =>
    to === '/i' ? pathname === '/i' || pathname === '/i/' : pathname.startsWith(to);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="mx-auto flex h-14 max-w-[1120px] items-center gap-6 px-4 md:px-10">
        <NavLink
          to="/i"
          aria-label="LlamaTrade, Today"
          className="flex flex-none items-center gap-3 text-fg"
        >
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
        <Avatar />
      </div>
    </header>
  );
}

/** Cross-fades the card body when it changes, so the Ask row above it never moves. */
function Swap({ k, children }: { k: string; children: ReactNode }) {
  const [cur, setCur] = useState(k);
  const [fresh, setFresh] = useState(false);
  if (cur !== k) {
    setCur(k);
    setFresh(true);
  }
  useEffect(() => {
    if (!fresh) return;
    const t = window.setTimeout(() => setFresh(false), 460);
    return () => window.clearTimeout(t);
  }, [fresh]);
  return (
    <div key={k} className={fresh ? 'i-in' : ''}>
      {children}
    </div>
  );
}

/** A quieter card under the main one, for the lists the page picks from. */
export function ListCard({
  title,
  meta,
  right,
  children,
}: {
  title: string;
  meta?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[14px] border border-line bg-canvas px-5 pb-4 pt-5 md:px-7 md:pb-5 md:pt-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="m-0 text-[15px] font-semibold tracking-[-0.01em] text-fg">{title}</h2>
          {meta && <div className="mt-0.5 text-[12.5px] text-fg-3">{meta}</div>}
        </div>
        {right && <div className="flex items-center gap-2">{right}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * Every page: the top bar, the chart art full bleed behind, and one crisp card centred over it.
 * The card's first row is the Ask line; its body is the page or, after a question, the conversation.
 */
export function Shell({
  pan,
  ask,
  bodyKey,
  body,
  below,
}: {
  /** Index of the tab, used to pan the art a little between tabs. */
  pan: number;
  ask: ReactNode;
  bodyKey: string;
  body: ReactNode;
  below?: ReactNode;
}) {
  const { pathname, search } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [pathname, search]);
  return (
    <div className="min-h-screen bg-canvas text-fg antialiased">
      <style>{MOTION}</style>
      <TopBar />
      <div
        aria-hidden="true"
        className="auth-aside fixed inset-x-0 bottom-0 top-14 overflow-hidden"
      >
        <div
          className="i-art absolute inset-y-0 -left-[8%] -right-[8%]"
          style={{ transform: `translateX(${(2 - pan) * 2.2}%)` }}
        >
          <AuthArt />
        </div>
      </div>
      <main className="relative mx-auto grid w-full max-w-[812px] grid-cols-[minmax(0,1fr)] gap-4 px-4 pb-28 pt-6 md:pt-10">
        <section className="auth-card relative w-full rounded-[14px] border bg-canvas">
          {ask}
          <div className="p-5 md:p-7">
            <Swap k={bodyKey}>{body}</Swap>
          </div>
        </section>
        {below}
      </main>
    </div>
  );
}
