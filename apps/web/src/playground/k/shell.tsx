import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { AuthArt } from '../../components/auth/AuthArt';
import { LogoMark } from '../../components/common/Logo';
import { MARKET } from '../data';

const NAV = [
  { to: '/k', label: 'Today' },
  { to: '/k/strategies', label: 'Strategies' },
  { to: '/k/backtests', label: 'Backtests' },
  { to: '/k/sessions', label: 'Sessions' },
  { to: '/k/portfolio', label: 'Portfolio' },
];

const MOTION = `
@keyframes k-in { from { opacity: 0; transform: translateY(14px) scale(0.985); } to { opacity: 1; transform: none; } }
@keyframes k-out { from { opacity: 1; transform: none; } to { opacity: 0; transform: translateY(-12px) scale(0.985); } }
@keyframes k-rail { from { opacity: 0; transform: translateX(8px); } to { opacity: 1; transform: none; } }
@keyframes k-pop { from { opacity: 0; transform: translateY(-6px) scale(0.99); } to { opacity: 1; transform: none; } }
@keyframes k-fade { from { opacity: 0; } to { opacity: 1; } }
.k-in { animation: k-in 0.52s cubic-bezier(0.2, 0.7, 0.2, 1) 0.08s both; }
.k-out { animation: k-out 0.3s cubic-bezier(0.4, 0, 1, 1) both; pointer-events: none; }
.k-rail { animation: k-rail 0.42s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
.k-pop { animation: k-pop 0.24s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
.k-fade { animation: k-fade 0.2s ease-out both; }
.k-art { transition: transform 1.1s cubic-bezier(0.2, 0.7, 0.2, 1); }
@media (prefers-reduced-motion: reduce) { .k-in, .k-out, .k-rail, .k-pop, .k-fade { animation: none; } .k-art { transition: none; } }
`;

function TopBar() {
  const spy = MARKET.quotes[0];
  const { pathname } = useLocation();
  const isOn = (to: string) =>
    to === '/k' ? pathname === '/k' || pathname === '/k/' : pathname.startsWith(to);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-6 px-4 md:px-10">
        <NavLink
          to="/k"
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
        <span className="grid h-7 w-7 flex-none place-items-center rounded-full border border-line-strong text-[11px] font-medium text-fg-2">
          NB
        </span>
      </div>
    </header>
  );
}

/**
 * Swaps the card: the old one lifts away while the new one rises in under the same light.
 * The leaving card is kept for the length of its exit.
 */
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
        <div key={`out-${leaving.k}`} aria-hidden="true" className="k-out absolute inset-x-0 top-0">
          {leaving.node}
        </div>
      )}
      <div key={k} className={leaving ? 'k-in' : ''}>
        {children}
      </div>
    </div>
  );
}

export interface Frame {
  cardKey: string;
  card: ReactNode;
  railKey: string;
  rail: ReactNode;
  askLine: ReactNode;
  /** The palette, laid over the Ask line and the card while open. */
  palette: ReactNode;
  paletteOpen: boolean;
  onClosePalette: () => void;
  /** Index of the tab, used to pan the art a little between tabs. */
  pan: number;
}

/** Top bar; then the card on the left two thirds over the art and a quiet rail of type beside it. */
export function Shell({
  cardKey,
  card,
  railKey,
  rail,
  askLine,
  palette,
  paletteOpen,
  onClosePalette,
  pan,
}: Frame) {
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [cardKey]);
  return (
    <div className="relative min-h-screen bg-canvas text-fg antialiased">
      <style>{MOTION}</style>
      <TopBar />
      <div
        aria-hidden="true"
        className="auth-aside fixed inset-x-0 bottom-0 top-14 overflow-hidden"
      >
        <div
          className="k-art absolute inset-y-0 -left-[6%] -right-[6%]"
          style={{ transform: `translateX(${(2 - pan) * 1.6}%)` }}
        >
          <AuthArt />
        </div>
      </div>
      {paletteOpen && (
        <div
          aria-hidden="true"
          onClick={onClosePalette}
          className="k-fade fixed inset-x-0 bottom-0 top-14 z-20 bg-canvas/60"
        />
      )}
      <main className="relative mx-auto grid max-w-[1320px] gap-x-14 gap-y-12 px-4 pb-28 pt-7 md:px-10 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_352px]">
        <div className="relative min-w-0">
          <div className="sticky top-[72px] z-10">{askLine}</div>
          <div className="mt-5">
            <Swap k={cardKey}>{card}</Swap>
          </div>
          {paletteOpen && <div className="absolute inset-x-0 top-0 z-30">{palette}</div>}
        </div>
        <aside aria-label="Overview" className="relative min-w-0 lg:pt-1">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -inset-x-16 -inset-y-10 bg-[radial-gradient(closest-side,rgb(var(--panel)/0.92)_55%,rgb(var(--panel)/0))]"
          />
          <div key={railKey} className="k-rail relative">
            {rail}
          </div>
        </aside>
      </main>
    </div>
  );
}
