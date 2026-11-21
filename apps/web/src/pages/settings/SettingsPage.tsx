import { usagePeriod } from '@llamatrade/core/billing/usage';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useSyncExternalStore, type ReactNode } from 'react';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { Avatar } from '../../components/common/Avatar';
import { ModeSegment } from '../../components/settings/AppearanceGrid';
import { PageHead, Tabs } from '../../components/ui';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAuthStore } from '../../store/auth';

import { brokerHeadline, readChecks } from './brokerLog';
import { etTime } from './health';
import { HealthCard } from './HealthCard';
import { MobileAccountList } from './MobileAccountList';
import { displayName, identityLine } from './model';
import { BackToAccount } from './parts';
import {
  DEFAULT_SECTION,
  SECTIONS,
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
import { useAccountIdentity } from './useAccountIdentity';
import { useSettingsSummary, type SettingsSummary } from './useSettingsSummary';

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

interface SectionHead {
  sub?: string;
  actions?: ReactNode;
}

/** The line under the tabs for each section, and the controls that belong beside it. */
function useSectionHead(key: SectionKey, { health, brokerLoaded }: SettingsSummary): SectionHead {
  const lastCheck = useBrokerStore((s) => s.lastCheck);
  switch (key) {
    case 'profile':
      return {};
    case 'broker': {
      if (!brokerLoaded) return {};
      const checkedAt = lastCheck?.at ?? readChecks()[0]?.at ?? null;
      return {
        sub: brokerHeadline(health.connected, health.problems.length, checkedAt, etTime),
      };
    }
    case 'notifications':
      return {
        sub: 'Everything appears in the app. Choose what also reaches you by email or webhook.',
      };
    case 'appearance':
      return {
        sub: 'Pick a surface and an accent for each mode. Saved on this device.',
        actions: <ModeSegment />,
      };
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

/** The person at the top of settings: avatar, name, email, workspace and when they joined. */
function AccountHeader() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const identity = useAccountIdentity();
  const name = displayName(user);
  const line = identityLine({
    email: user?.email,
    workspace: identity.workspace,
    memberSince: identity.memberSince,
  });
  return (
    <header className="flex items-center gap-[18px]">
      <Avatar
        avatarUrl={user?.avatarUrl}
        firstName={user?.firstName}
        lastName={user?.lastName}
        email={user?.email}
        size={64}
        className="flex-none text-[20px]"
      />
      <div className="min-w-0 flex-1">
        <h1 className="m-0 truncate text-[27px] leading-tight">
          {name || user?.email || 'Account'}
        </h1>
        {line && <p className="m-0 mt-1 truncate text-[13px] text-fg-3">{line}</p>}
      </div>
      <button
        type="button"
        className="btn btn-secondary flex-none"
        onClick={() => {
          logout();
          navigate('/');
        }}
      >
        Sign out
      </button>
    </header>
  );
}

/** Desktop: one header, five tabs (shell2 C). Phone: a pushed page back to the Account list. */
function SettingsShell({ active, children }: { active: SectionKey; children: ReactNode }) {
  const navigate = useNavigate();
  const settings = useSettingsSummary();
  const { summary, brokerLoaded } = settings;
  const head = useSectionHead(active, settings);
  useDocumentTitle(sectionLabel(active));
  return (
    <div className="page mx-auto max-w-[1080px]">
      <div className="hidden md:block">
        <AccountHeader />
        {brokerLoaded && summary.tone === 'risk' && active !== 'broker' && (
          <div className="mt-5">
            <HealthCard summary={summary} />
          </div>
        )}
        <Tabs
          label="Settings"
          className="mt-6"
          value={active}
          onChange={(key) => navigate(sectionPath(key))}
          options={SECTIONS.map((s) => ({ key: s.key, label: s.label }))}
        />
        {(head.sub || head.actions) && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            {head.sub && <p className="m-0 text-[13px] text-fg-2">{head.sub}</p>}
            {head.actions && <div className="ml-auto flex-none">{head.actions}</div>}
          </div>
        )}
      </div>
      <div className="md:hidden">
        <BackToAccount />
        <PageHead title={sectionLabel(active)} sub={head.sub} actions={head.actions} />
      </div>
      <div className="mt-0 md:mt-5">{children}</div>
    </div>
  );
}

/** /settings: the Account list on a phone; on a wider screen it opens Profile. */
function SettingsIndex() {
  const desktop = useIsDesktop();
  if (!desktop) return <MobileAccountList />;
  return <Navigate to={sectionPath(DEFAULT_SECTION)} replace />;
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
