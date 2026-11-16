import { useSyncExternalStore, type ReactNode } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';

import { useAuthStore } from '../../store/auth';

import { MobileAccountList } from './MobileAccountList';
import { BackToAccount } from './parts';
import {
  DEFAULT_SECTION,
  SECTION_GROUPS,
  resolveSection,
  sectionLabel,
  sectionPath,
  type SectionKey,
} from './sections';
import { AppearanceSection } from './sections/AppearanceSection';
import { BrokerSection } from './sections/BrokerSection';
import { NotificationsSection } from './sections/NotificationsSection';
import { PlanSection } from './sections/PlanSection';
import { ProfileSection } from './sections/ProfileSection';

const SECTION_VIEW: Record<SectionKey, () => ReactNode> = {
  profile: () => <ProfileSection />,
  broker: () => <BrokerSection />,
  notifications: () => <NotificationsSection />,
  appearance: () => <AppearanceSection />,
  plan: () => <PlanSection />,
};

const DESKTOP_QUERY = '(min-width: 768px)';

function subscribeDesktop(onChange: () => void): () => void {
  const mq = window.matchMedia(DESKTOP_QUERY);
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}

function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribeDesktop,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => false
  );
}

/** /settings: the Account list on a phone, the first section on a wider screen. */
function SettingsIndex() {
  const desktop = useIsDesktop();
  if (desktop) return <Navigate to={sectionPath(DEFAULT_SECTION)} replace />;
  return <MobileAccountList />;
}

export function SettingsSidebar({ active }: { active: SectionKey }) {
  return (
    <nav aria-label="Settings" className="hidden content-start gap-0.5 md:grid">
      {SECTION_GROUPS.map((group, gi) => (
        <div key={group.label} className="contents">
          <span
            className={`px-2.5 pb-1 text-[11px] font-medium text-fg-3 ${gi === 0 ? '' : 'pt-3'}`}
          >
            {group.label}
          </span>
          {group.items.map((item) => {
            const on = item.key === active;
            const Icon = item.icon;
            return (
              <Link
                key={item.key}
                to={sectionPath(item.key)}
                aria-current={on ? 'page' : undefined}
                className={`flex items-center gap-[9px] rounded-[6px] px-2.5 py-[7px] text-[13px] transition-colors ${
                  on ? 'bg-sunk text-fg' : 'text-fg-2 hover:text-fg'
                }`}
              >
                <Icon className="h-4 w-4 flex-none" strokeWidth={1.7} />
                {item.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function SettingsShell({ active, children }: { active: SectionKey; children: ReactNode }) {
  const email = useAuthStore((s) => s.user?.email);
  return (
    <div className="page">
      <div className="mb-4 hidden md:block">
        <h1 className="m-0 text-[21px] leading-tight">Settings</h1>
        {email && <div className="mt-[3px] text-[12.5px] text-fg-3">Signed in as {email}</div>}
      </div>
      <div className="mb-3 md:hidden">
        <BackToAccount />
        <h1 className="m-0 text-[27px] leading-tight">{sectionLabel(active)}</h1>
      </div>
      <div className="grid gap-6 md:grid-cols-[210px_minmax(0,1fr)]">
        <SettingsSidebar active={active} />
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}

/** Settings at /settings and /settings/:section. A legacy ?tab= still opens its section. */
export default function SettingsPage() {
  const { section } = useParams();
  const [params] = useSearchParams();
  const requested = section ?? params.get('tab');
  const key = resolveSection(requested);

  if (requested && !key) return <Navigate to={sectionPath(DEFAULT_SECTION)} replace />;
  if (!key) return <SettingsIndex />;
  return <SettingsShell active={key}>{SECTION_VIEW[key]()}</SettingsShell>;
}
