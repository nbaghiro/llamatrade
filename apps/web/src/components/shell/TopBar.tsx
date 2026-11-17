import { Search } from 'lucide-react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import { activeDestination, DESKTOP_NAV } from '../../lib/navigation';
import { LogoMark } from '../common/Logo';
import { NotificationBell } from '../notifications/NotificationBell';
import { Kbd } from '../ui/Kbd';

import { AccountMenu } from './AccountMenu';
import { useAreaMarks, type AreaMark } from './attention';
import { BarClock } from './BarClock';
import { usePalette } from './usePalette';

function markLabel(label: string, marks: readonly AreaMark[] | undefined): string {
  if (!marks?.length) return label;
  return `${label}, ${marks.length} ${marks.length === 1 ? 'needs' : 'need'} attention`;
}

function AreaFlag({ marks }: { marks: readonly AreaMark[] | undefined }) {
  if (!marks?.length) return null;
  return (
    <span aria-hidden="true" className="inline-flex items-center gap-1">
      <i className="h-1.5 w-1.5 rounded-full bg-risk shadow-[0_0_0_3px_var(--risk-soft)]" />
      {marks.length > 1 && (
        <b className="font-mono text-[10.5px] font-semibold text-risk">{marks.length}</b>
      )}
    </span>
  );
}

/** The logo, then the seven areas as text links on the left, with the market clock beside search. */
export function TopBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const showPalette = usePalette((s) => s.show);
  const active = activeDestination(pathname, DESKTOP_NAV);
  const marks = useAreaMarks();

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-line bg-canvas/95 px-4 backdrop-blur md:px-5">
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
          <LogoMark size={34} bold className="-my-2" />
          <span className="hidden whitespace-nowrap text-[12px] font-semibold uppercase leading-none tracking-[0.16em] min-[1360px]:inline">
            LlamaTrade
          </span>
        </span>
      </a>

      <nav aria-label="Main" className="ml-3 hidden min-w-0 md:flex md:gap-0.5 lg:ml-7">
        {DESKTOP_NAV.map((d) => {
          const on = active === d.key;
          const areaMarks = marks[d.key];
          return (
            <NavLink
              key={d.key}
              to={d.to}
              aria-current={on ? 'page' : undefined}
              aria-label={markLabel(d.label, areaMarks)}
              title={areaMarks?.map((m) => m.title).join('\n') || d.label}
              className={`relative inline-flex items-center gap-[7px] whitespace-nowrap rounded-md px-2.5 py-1.5 text-[14px] transition-colors xl:px-3 ${
                on ? 'font-semibold text-fg' : 'text-fg-2 hover:text-fg'
              }`}
            >
              {d.label}
              <AreaFlag marks={areaMarks} />
            </NavLink>
          );
        })}
      </nav>

      <div className="ml-auto flex flex-none items-center gap-1.5 sm:gap-2">
        <BarClock className="max-[340px]:hidden" />
        <button
          type="button"
          onClick={showPalette}
          aria-label="Search or jump to"
          className="flex h-[34px] items-center gap-2 rounded-full border border-line bg-panel px-2.5 text-fg-3 hover:text-fg-2"
        >
          <Search className="h-4 w-4" />
          <span className="hidden text-[13px] min-[1440px]:inline">Search</span>
          <Kbd className="hidden min-[1440px]:inline">⌘K</Kbd>
        </button>
        <span className="hidden md:contents">
          <NotificationBell />
          <AccountMenu />
        </span>
      </div>
    </header>
  );
}
