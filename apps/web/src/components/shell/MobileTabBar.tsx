import { Link, useLocation } from 'react-router-dom';

import { activeDestination, MOBILE_TABS } from '../../lib/navigation';

import { DESTINATION_ICON } from './icons';

/** Five tabs under 768px. Backtests live inside Strategies and Sessions inside Portfolio. */
export function MobileTabBar() {
  const { pathname } = useLocation();
  const active = activeDestination(pathname, MOBILE_TABS);
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line bg-canvas/95 px-1.5 pt-2 backdrop-blur md:hidden"
      style={{ paddingBottom: 'max(8px, env(safe-area-inset-bottom))' }}
    >
      {MOBILE_TABS.map((t) => {
        const Icon = DESTINATION_ICON[t.key];
        const on = active === t.key;
        return (
          <Link
            key={t.key}
            to={t.to}
            aria-current={on ? 'page' : undefined}
            className={`flex flex-col items-center gap-1 text-[10.5px] font-medium ${on ? 'text-accent' : 'text-fg-3'}`}
          >
            <Icon className="h-[22px] w-[22px]" strokeWidth={1.6} />
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
