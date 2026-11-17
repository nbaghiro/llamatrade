import { usagePeriod } from '@llamatrade/core/billing/usage';
import { LayoutGrid } from 'lucide-react';
import { useSyncExternalStore, type ReactNode } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';

import { PageHead } from '../../components/ui';

import { MobileAccountList } from './MobileAccountList';
import { SettingsOverview } from './Overview';
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
import { useSettingsSummary, type SectionState } from './useSettingsSummary';

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

const fullDay = (d: Date) => d.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });

function sectionHead(key: SectionKey): { sub: string; actions?: ReactNode } {
  switch (key) {
    case 'profile':
      return { sub: 'Who you are in LlamaTrade and how you sign in.' };
    case 'broker':
      return { sub: 'Your Alpaca accounts. Each session trades on one of them.' };
    case 'notifications':
      return {
        sub: 'Everything appears in the app. Choose what also reaches you by email or webhook.',
      };
    case 'appearance':
      return { sub: 'Saved on this device.' };
    case 'plan': {
      const { start, end } = usagePeriod(new Date());
      const reset = new Date(end.getFullYear(), end.getMonth() + 1, 1);
      return {
        sub: `${fullDay(start)} to ${end.getDate()} · resets ${fullDay(reset)}`,
        actions: (
          <Link to="/settings/plans" className="btn btn-secondary">
            Compare plans
          </Link>
        ),
      };
    }
  }
}

function SideState({ state }: { state: SectionState | null }) {
  if (!state) return null;
  return (
    <span
      className={`ml-auto truncate pl-2 text-[11.5px] ${state.risk ? 'text-risk' : 'text-fg-3'}`}
    >
      {state.text}
    </span>
  );
}

const SIDE_ITEM =
  'flex items-center gap-[9px] rounded-[6px] px-2.5 py-[7px] text-[13px] transition-colors';
const sideTone = (on: boolean) => (on ? 'bg-sunk text-fg' : 'text-fg-2 hover:text-fg');

/** The settings sidebar; each item carries its section's current state (shell2 A). */
export function SettingsSidebar({ active }: { active: SectionKey | null }) {
  const { states } = useSettingsSummary();
  return (
    <nav aria-label="Settings" className="hidden content-start gap-0.5 md:grid">
      <Link
        to="/settings"
        aria-current={active === null ? 'page' : undefined}
        className={`${SIDE_ITEM} ${sideTone(active === null)}`}
      >
        <LayoutGrid className="h-4 w-4 flex-none" strokeWidth={1.7} />
        Overview
      </Link>
      {SECTION_GROUPS.map((group) => (
        <div key={group.label} className="contents">
          <span className="px-2.5 pb-1 pt-3 text-[11px] font-medium text-fg-3">{group.label}</span>
          {group.items.map((item) => {
            const on = item.key === active;
            const Icon = item.icon;
            return (
              <Link
                key={item.key}
                to={sectionPath(item.key)}
                aria-current={on ? 'page' : undefined}
                className={`${SIDE_ITEM} ${sideTone(on)}`}
              >
                <Icon className="h-4 w-4 flex-none" strokeWidth={1.7} />
                <span className="truncate">{item.label}</span>
                <SideState state={states[item.key]} />
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function SettingsShell({ active, children }: { active: SectionKey | null; children: ReactNode }) {
  const head = active ? sectionHead(active) : null;
  return (
    <div className="page">
      <div className="grid gap-7 md:grid-cols-[230px_minmax(0,1fr)]">
        <SettingsSidebar active={active} />
        <div className="min-w-0">
          {active && head && (
            <>
              <BackToAccount />
              <PageHead title={sectionLabel(active)} sub={head.sub} actions={head.actions} />
            </>
          )}
          {children}
        </div>
      </div>
    </div>
  );
}

/** /settings: the Account list on a phone, the overview on a wider screen. */
function SettingsIndex() {
  const desktop = useIsDesktop();
  if (!desktop) return <MobileAccountList />;
  return (
    <SettingsShell active={null}>
      <SettingsOverview />
    </SettingsShell>
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
