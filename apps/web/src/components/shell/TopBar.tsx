import { Search } from 'lucide-react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import { activeDestination, DESKTOP_NAV } from '../../lib/navigation';
import { LogoMark } from '../common/Logo';
import { NotificationBell } from '../notifications/NotificationBell';
import { Kbd } from '../ui/Kbd';

import { AccountMenu } from './AccountMenu';
import { MarketStatusChip } from './MarketStatusChip';
import { PaperPill } from './PaperPill';
import { usePalette } from './usePalette';

export function TopBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const showPalette = usePalette((s) => s.show);
  const active = activeDestination(pathname, DESKTOP_NAV);

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-line bg-canvas/95 px-4 backdrop-blur md:px-[22px] lg:gap-[26px]">
      <a
        href="/home"
        aria-label="LlamaTrade home"
        className="flex-none"
        onClick={(e) => {
          // First click goes to Home; a second click on Home opens the marketing page at /home.
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
          if (pathname !== '/dashboard') {
            e.preventDefault();
            navigate('/dashboard');
          }
        }}
      >
        <span className="flex items-center gap-3 text-fg">
          <LogoMark size={32} bold className="-my-1.5" />
          {/* The wordmark gives way where the bar is tightest: small phones and tablets. */}
          <span className="whitespace-nowrap text-[11.5px] font-semibold uppercase leading-none tracking-[0.16em] max-[359px]:hidden md:max-lg:hidden">
            LlamaTrade
          </span>
        </span>
      </a>

      <nav aria-label="Main" className="hidden gap-0.5 md:flex">
        {DESKTOP_NAV.map((d) => (
          <NavLink
            key={d.key}
            to={d.to}
            aria-current={active === d.key ? 'page' : undefined}
            className={`nav-link ${active === d.key ? 'nav-link-active' : ''}`}
          >
            {d.label}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex flex-none items-center gap-2 sm:gap-3">
        <MarketStatusChip className="hidden xl:inline-flex" />
        <button
          type="button"
          onClick={showPalette}
          aria-label="Search or jump to"
          className="flex h-8 items-center gap-2 rounded-[8px] border border-line bg-panel pl-2.5 pr-2 text-fg-3 hover:text-fg-2 lg:min-w-[200px]"
        >
          <Search className="h-4 w-4" />
          <span className="hidden text-[13px] lg:inline">Search or jump to</span>
          <Kbd className="ml-auto hidden lg:inline">⌘K</Kbd>
        </button>
        <NotificationBell />
        <PaperPill />
        <AccountMenu />
      </div>
    </header>
  );
}
