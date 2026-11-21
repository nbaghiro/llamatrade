import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import { AuthArt } from '../../components/auth/AuthArt';
import { LogoMark } from '../../components/common/Logo';
import { MARKET } from '../data';

const NAV = [
  { to: '/j', label: 'Today' },
  { to: '/j/strategies', label: 'Strategies' },
  { to: '/j/backtests', label: 'Backtests' },
  { to: '/j/sessions', label: 'Sessions' },
  { to: '/j/portfolio', label: 'Portfolio' },
];

const MOTION = `
@keyframes j-in { from { opacity: 0; transform: translateY(14px) scale(0.985); } to { opacity: 1; transform: none; } }
@keyframes j-out { from { opacity: 1; transform: none; } to { opacity: 0; transform: translateY(-12px) scale(0.985); } }
.j-in { animation: j-in 0.52s cubic-bezier(0.2, 0.7, 0.2, 1) 0.08s both; }
.j-out { animation: j-out 0.3s cubic-bezier(0.4, 0, 1, 1) both; pointer-events: none; }
.j-art { transition: transform 1.1s cubic-bezier(0.2, 0.7, 0.2, 1); }
@media (prefers-reduced-motion: reduce) { .j-in, .j-out { animation: none; } .j-art { transition: none; } }
`;

/** Shared width of the card, the second card and the docked composer. */
export const COLUMN = 'mx-auto w-full max-w-[720px] px-4';

function Avatar() {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
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
            onClick={() => {
              setOpen(false);
              nav('/j');
            }}
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
    to === '/j' ? pathname === '/j' || pathname === '/j/' : pathname.startsWith(to);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-6 px-4 md:px-8">
        <NavLink
          to="/j"
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

/** Swaps the card: the old one lifts away while the new one rises in under the same light. */
function Swap({ k, children }: { k: string; children: ReactNode }) {
  const [cur, setCur] = useState(k);
  const [leaving, setLeaving] = useState<{ k: string; node: ReactNode } | null>(null);
  const [lastNode, setLastNode] = useState<ReactNode>(children);
  if (cur !== k) {
    setLeaving({ k: cur, node: lastNode });
    setCur(k);
  }
  useEffect(() => {
    setLastNode(children);
  }, [children]);
  useEffect(() => {
    if (!leaving) return;
    const t = window.setTimeout(() => setLeaving(null), 320);
    return () => window.clearTimeout(t);
  }, [leaving]);
  return (
    <div className="relative w-full">
      {leaving && (
        <div key={`out-${leaving.k}`} aria-hidden="true" className="j-out absolute inset-x-0 top-0">
          {leaving.node}
        </div>
      )}
      <div key={k} className={leaving ? 'j-in' : ''}>
        {children}
      </div>
    </div>
  );
}

/** Top bar, the chart art across the whole page, one card centred over it and the composer under it. */
export function Shell({
  stageKey,
  stage,
  below,
  composer,
  pan,
}: {
  stageKey: string;
  stage: ReactNode;
  /** The smaller second card under the main one. */
  below?: ReactNode;
  composer: ReactNode;
  /** Index of the tab, used to pan the art a little between tabs. */
  pan: number;
}) {
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [stageKey]);
  return (
    <div className="min-h-screen overflow-x-clip bg-canvas text-fg antialiased">
      <style>{MOTION}</style>
      <TopBar />
      <div
        aria-hidden="true"
        className="auth-aside fixed inset-x-0 bottom-0 top-14 overflow-hidden"
      >
        <div
          className="j-art absolute inset-y-0 -left-[8%] -right-[8%]"
          style={{ transform: `translateX(${(2 - pan) * 2.2}%)` }}
        >
          <AuthArt />
        </div>
      </div>
      <main className={`relative ${COLUMN} pb-[232px] pt-6 md:pb-[200px] md:pt-8`}>
        <Swap k={stageKey}>{stage}</Swap>
        {below && (
          <div key={`below-${stageKey.split(':')[0]}`} className="mt-5 animate-rise">
            {below}
          </div>
        )}
      </main>
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 h-[230px] bg-gradient-to-t from-panel from-40% via-panel/90 to-transparent md:h-[160px]" />
      <div className="fixed inset-x-0 bottom-16 z-30 md:bottom-5">
        <div className={COLUMN}>{composer}</div>
      </div>
    </div>
  );
}
