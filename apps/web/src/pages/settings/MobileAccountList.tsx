import { ChevronRight } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { Avatar } from '../../components/common/Avatar';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAuthStore } from '../../store/auth';

import { HealthCard } from './HealthCard';
import { displayName } from './model';
import { MobileRow } from './parts';
import { SECTIONS, sectionPath } from './sections';
import { useAccountIdentity } from './useAccountIdentity';
import { useSectionDetails } from './useSectionDetails';
import { useSettingsSummary } from './useSettingsSummary';

/** The Account tab on a phone: whether anything needs you, who's signed in, then each section. */
export function MobileAccountList() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { summary, states, brokerLoaded } = useSettingsSummary();
  const details = useSectionDetails();
  const { workspace } = useAccountIdentity();
  useDocumentTitle('Account');

  const name = displayName(user);

  return (
    <div className="flex min-h-[calc(100dvh-140px)] flex-col gap-3 px-4 py-5">
      <h1 className="m-0 text-[27px] leading-tight">Account</h1>
      {brokerLoaded && <HealthCard summary={summary} />}
      <Link
        to={sectionPath('profile')}
        className="flex items-center gap-3 rounded-[13px] border border-line bg-panel px-4 py-3.5"
      >
        <Avatar
          avatarUrl={user?.avatarUrl}
          firstName={user?.firstName}
          lastName={user?.lastName}
          email={user?.email}
          size={44}
        />
        <span className="min-w-0 flex-1">
          {name && <b className="block truncate text-[16px] font-semibold">{name}</b>}
          <span className="block truncate text-[13.5px] text-fg-3">{user?.email}</span>
          {workspace && (
            <span className="block truncate text-[13.5px] text-fg-3">{workspace} workspace</span>
          )}
        </span>
        <ChevronRight aria-hidden="true" className="h-4 w-4 text-fg-3" />
      </Link>

      <nav aria-label="Account" className="rounded-[13px] border border-line bg-panel px-4 py-0.5">
        {SECTIONS.filter((s) => s.key !== 'profile').map((s) => {
          const state = states[s.key];
          const value = details[s.key].value ?? state?.text;
          return (
            <Link key={s.key} to={sectionPath(s.key)} className="block">
              <MobileRow
                end={
                  <>
                    {value && (
                      <span className={`truncate ${state?.risk ? 'text-risk' : 'text-fg-3'}`}>
                        {value}
                      </span>
                    )}
                    <ChevronRight className="h-4 w-4 text-fg-3" />
                  </>
                }
              >
                <span className="flex items-center gap-3">
                  <s.icon aria-hidden="true" className="h-4 w-4 text-fg-3" strokeWidth={1.7} />
                  {s.label}
                </span>
              </MobileRow>
            </Link>
          );
        })}
      </nav>

      <button
        type="button"
        className="mt-auto h-[50px] rounded-[12px] border border-line-strong bg-panel text-[15.5px] font-semibold text-fg"
        onClick={() => {
          logout();
          navigate('/');
        }}
      >
        Sign out
      </button>
    </div>
  );
}
