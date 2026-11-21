import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';

import { AuthArt } from '../../components/auth/AuthArt';
import { LogoMark } from '../../components/common/Logo';
import { MARKET } from '../data';

const NAV = [
  { to: '/g', label: 'Today' },
  { to: '/g/strategies', label: 'Strategies' },
  { to: '/g/backtests', label: 'Backtests' },
  { to: '/g/sessions', label: 'Sessions' },
  { to: '/g/portfolio', label: 'Portfolio' },
];

const MOTION = `
@keyframes g-in { from { opacity: 0; transform: translateY(14px) scale(0.985); } to { opacity: 1; transform: none; } }
@keyframes g-out { from { opacity: 1; transform: none; } to { opacity: 0; transform: translateY(-12px) scale(0.985); } }
@keyframes g-left { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: none; } }
.g-in { animation: g-in 0.52s cubic-bezier(0.2, 0.7, 0.2, 1) 0.08s both; }
.g-out { animation: g-out 0.3s cubic-bezier(0.4, 0, 1, 1) both; pointer-events: none; }
.g-left { animation: g-left 0.42s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
.g-art { transition: transform 1.1s cubic-bezier(0.2, 0.7, 0.2, 1); }
@media (prefers-reduced-motion: reduce) { .g-in, .g-out, .g-left { animation: none; } .g-art { transition: none; } }
`;

function Brand() {
  return (
    <Link
      to="/g"
      aria-label="LlamaTrade, Today"
      className="inline-flex items-center gap-3.5 text-fg"
    >
      <LogoMark size={44} bold className="-my-2" />
      <span className="text-[12.5px] font-semibold uppercase leading-none tracking-[0.16em]">
        LlamaTrade
      </span>
    </Link>
  );
}

function Avatar() {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Account menu"
        className="grid h-8 w-8 place-items-center rounded-full border border-line-strong text-[11px] font-medium text-fg-2 hover:text-fg"
      >
        NB
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-30 grid w-44 animate-rise gap-0.5 rounded-[10px] border border-line-strong bg-canvas p-1 text-[13px] shadow-lg">
          <span className="px-2.5 py-1.5 text-[12px] text-fg-3">naib@llamatrade.dev</span>
          <button
            type="button"
            onClick={() => nav('/g/signin')}
            className="rounded-[6px] px-2.5 py-1.5 text-left text-fg hover:bg-sunk"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Nav() {
  const { pathname } = useLocation();
  const isOn = (to: string) =>
    to === '/g' ? pathname === '/g' || pathname === '/g/' : pathname.startsWith(to);
  return (
    <nav className="-mx-2.5 flex items-center gap-0.5 overflow-x-auto">
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          className={`whitespace-nowrap rounded-full px-2.5 py-1 text-[13px] transition-colors ${
            isOn(n.to) ? 'bg-sunk font-medium text-fg' : 'text-fg-3 hover:text-fg'
          }`}
        >
          {n.label}
        </NavLink>
      ))}
    </nav>
  );
}

/**
 * Swaps the stage panel: the old panel lifts away while the new one rises in under the same light.
 * The leaving panel is the last rendered element, kept for the length of its exit.
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
        <div key={`out-${leaving.k}`} aria-hidden="true" className="g-out absolute inset-x-0 top-0">
          {leaving.node}
        </div>
      )}
      <div key={k} className={leaving ? 'g-in' : ''}>
        {children}
      </div>
    </div>
  );
}

export interface Split {
  /** Changes when the left column shows a different page, so it rises in again. */
  leftKey: string;
  left: ReactNode;
  composer?: ReactNode;
  stageKey: string;
  stage: ReactNode;
  /** Index of the tab, used to pan the art behind the stage a little between tabs. */
  pan: number;
  nav?: boolean;
  foot?: ReactNode;
  wide?: boolean;
}

/** Every page is the sign-in screen: the essentials on the left, one object on the stage. */
export function Shell({
  leftKey,
  left,
  composer,
  stageKey,
  stage,
  pan,
  nav = true,
  foot,
  wide,
}: Split) {
  const body = useRef<HTMLDivElement>(null);
  const stageScroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    stageScroll.current?.scrollTo({ top: 0 });
  }, [stageKey]);
  useEffect(() => {
    body.current?.scrollTo({ top: 0 });
  }, [leftKey]);
  const spy = MARKET.quotes[0];
  return (
    <div className="auth-shell bg-canvas text-fg antialiased md:grid md:h-screen md:grid-cols-[400px_minmax(0,1fr)] lg:grid-cols-[440px_minmax(0,1fr)]">
      <style>{MOTION}</style>
      <aside className="flex min-h-0 flex-col md:h-screen md:border-r md:border-line">
        <div className="flex items-center justify-between px-4 pt-5 md:px-9 md:pt-[26px]">
          <Brand />
          {nav && <Avatar />}
        </div>
        {nav && (
          <div className="mt-5 px-4 md:px-9">
            <Nav />
          </div>
        )}
        <div
          ref={body}
          className="min-h-0 flex-1 overflow-y-auto px-4 pb-6 pt-7 md:px-9 md:[mask-image:linear-gradient(to_bottom,#000_calc(100%-28px),transparent)]"
        >
          <div key={leftKey} className="g-left">
            {left}
          </div>
        </div>
        {composer && <div className="px-4 pb-3 pt-1 md:px-9">{composer}</div>}
        <div aria-hidden="true" className="hidden h-[60px] flex-none md:block" />
      </aside>
      <main className="auth-aside relative min-h-[560px] overflow-hidden md:h-screen">
        <div
          className="g-art absolute inset-y-0 -left-[8%] -right-[8%]"
          style={{ transform: `translateX(${(2 - pan) * 2.2}%)` }}
        >
          <AuthArt />
        </div>
        <div className="pointer-events-none absolute right-5 top-5 z-10 hidden text-[12px] text-fg-3 md:block lg:right-7 lg:top-[26px]">
          {foot ?? (
            <span className="inline-flex items-center gap-3 font-mono text-[11.5px] tabular-nums">
              <span className="inline-flex items-center gap-1.5">
                <i className="h-1.5 w-1.5 rounded-full bg-gain" aria-hidden="true" />
                {MARKET.status}
              </span>
              <span className="text-fg-2">
                SPY {spy.price.toFixed(2)}{' '}
                <span className="text-loss">−{Math.abs(spy.change * 100).toFixed(2)}%</span>
              </span>
            </span>
          )}
        </div>
        <div ref={stageScroll} className="relative h-full overflow-y-auto">
          <div className="flex min-h-full flex-col items-center justify-center px-4 py-10 md:px-10 lg:px-14">
            <div className={`w-full ${wide ? 'max-w-[780px]' : 'max-w-[700px]'}`}>
              <Swap k={stageKey}>{stage}</Swap>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
