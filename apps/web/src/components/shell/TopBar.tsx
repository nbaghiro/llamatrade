import { Snowflake } from 'lucide-react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';

import { activeDestination, DESKTOP_NAV } from '../../lib/navigation';
import { useAuthStore } from '../../store/auth';
import { Avatar } from '../common/Avatar';
import { BrandLockup, LogoMark } from '../common/Logo';
import { NotificationBell } from '../notifications/NotificationBell';

import { AccountMenu } from './AccountMenu';
import {
  isFrozenMark,
  useAreaMarks,
  useSeamNotice,
  type AreaMark,
  type SeamNotice,
} from './attention';
import { MarketStatus } from './MarketStatus';

const flagged = (marks: readonly AreaMark[] | undefined) =>
  (marks ?? []).filter((m) => !isFrozenMark(m));

function markLabel(label: string, marks: readonly AreaMark[]): string {
  if (!marks.length) return label;
  return `${label}, ${marks.length} ${marks.length === 1 ? 'needs' : 'need'} attention`;
}

function AreaFlag({ marks }: { marks: readonly AreaMark[] }) {
  if (!marks.length) return null;
  return (
    <span aria-hidden="true" className="inline-flex items-center gap-1">
      <i className="h-1.5 w-1.5 rounded-full bg-risk shadow-[0_0_0_3px_var(--risk-soft)]" />
      {marks.length > 1 && (
        <b className="font-mono text-[10.5px] font-semibold text-risk">{marks.length}</b>
      )}
    </span>
  );
}

/** A 2px amber edge under the bar with a tab at its right end that opens the review (attention2 B). */
export function Seam({ notice }: { notice: SeamNotice }) {
  return (
    <div role="status" className="relative h-0.5 bg-risk">
      <Link
        to={notice.href}
        className="absolute right-3 top-0.5 inline-flex h-[26px] max-w-[calc(100vw-24px)] items-center gap-2 overflow-hidden whitespace-nowrap rounded-b-[8px] border border-t-0 border-risk-line bg-panel px-3 text-[12px] text-fg-2 shadow-sm hover:text-fg md:right-5"
      >
        <Snowflake aria-hidden="true" className="h-[13px] w-[13px] flex-none text-risk" />
        <b className="font-semibold text-risk">{notice.title}</b>
        <span className="hidden truncate sm:inline">
          {notice.detail}
          {notice.more > 0 && `, and ${notice.more} more`}
        </span>
        <span className="text-fg underline decoration-line-strong underline-offset-[3px]">
          Review
        </span>
      </Link>
    </div>
  );
}

/** On a phone the avatar opens the Account list (phone-nav2 A). */
function PhoneAvatar() {
  const user = useAuthStore((s) => s.user);
  return (
    <Link to="/settings" aria-label="Account" className="rounded-full md:hidden">
      <Avatar
        avatarUrl={user?.avatarUrl}
        firstName={user?.firstName}
        lastName={user?.lastName}
        email={user?.email}
        size={30}
      />
    </Link>
  );
}

/**
 * The logo and five areas on the left; the market status, the bell and the account on the right.
 * A frozen sleeve turns the bottom edge amber.
 */
export function TopBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const active = activeDestination(pathname, DESKTOP_NAV);
  const marks = useAreaMarks();
  const seam = useSeamNotice();

  return (
    <div className="sticky top-0 z-40">
      <header
        className={`flex h-14 items-center gap-3 bg-canvas/90 px-4 backdrop-blur md:px-6 ${seam ? '' : 'border-b border-line/70'}`}
      >
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
          <span className="hidden md:inline">
            <BrandLockup wordClassName="hidden min-[1280px]:inline" />
          </span>
          <LogoMark size={28} bold className="md:hidden" />
        </a>

        <nav aria-label="Main" className="ml-3 hidden min-w-0 md:flex md:gap-1 lg:ml-8">
          {DESKTOP_NAV.map((d) => {
            const on = active === d.key;
            const areaMarks = flagged(marks[d.key]);
            return (
              <NavLink
                key={d.key}
                to={d.to}
                aria-current={on ? 'page' : undefined}
                aria-label={markLabel(d.label, areaMarks)}
                title={areaMarks.map((m) => m.title).join('\n') || d.label}
                className={`relative inline-flex items-center gap-[7px] whitespace-nowrap rounded-full px-3 py-[5px] text-[13.5px] transition-colors ${
                  on ? 'bg-sunk font-semibold text-fg' : 'text-fg-3 hover:text-fg'
                }`}
              >
                {d.label}
                <AreaFlag marks={areaMarks} />
              </NavLink>
            );
          })}
        </nav>

        <div className="ml-auto flex flex-none items-center gap-1 sm:gap-3">
          <MarketStatus />
          <NotificationBell />
          <span className="hidden md:contents">
            <AccountMenu />
          </span>
          <PhoneAvatar />
        </div>
      </header>
      {seam && <Seam notice={seam} />}
    </div>
  );
}
