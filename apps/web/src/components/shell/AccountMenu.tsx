import { useBillingStore } from '@llamatrade/core/stores/billing';
import { CreditCard, LogOut, Palette, Settings } from 'lucide-react';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuthStore } from '../../store/auth';
import { Avatar } from '../common/Avatar';
import { Menu } from '../ui/Menu';

export function AccountMenu() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const subscription = useBillingStore((s) => s.subscription);
  const fetchSubscription = useBillingStore((s) => s.fetchSubscription);

  useEffect(() => {
    fetchSubscription().catch(() => undefined);
  }, [fetchSubscription]);

  const name = [user?.firstName, user?.lastName].filter(Boolean).join(' ');
  const plan = subscription?.plan?.name;

  return (
    <Menu
      label="Account"
      width={260}
      trigger={(props) => (
        <button type="button" {...props} aria-label="Account" className="rounded-full">
          <Avatar
            avatarUrl={user?.avatarUrl}
            firstName={user?.firstName}
            lastName={user?.lastName}
            email={user?.email}
            size={30}
          />
        </button>
      )}
      header={
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
          <Avatar
            avatarUrl={user?.avatarUrl}
            firstName={user?.firstName}
            lastName={user?.lastName}
            email={user?.email}
            size={32}
          />
          <div className="min-w-0">
            {name && <b className="block truncate text-[13px] font-semibold">{name}</b>}
            <div className="truncate text-xs text-fg-3">{user?.email}</div>
            <div className="mt-0.5 text-xs text-fg-3">
              {plan ? `${plan} plan · Paper` : 'Paper'}
            </div>
          </div>
        </div>
      }
      items={[
        { kind: 'link', label: 'Settings', to: '/settings/profile', icon: Settings },
        { kind: 'link', label: 'Plan and usage', to: '/settings/plan', icon: CreditCard },
        { kind: 'link', label: 'Appearance', to: '/settings/appearance', icon: Palette },
        { kind: 'divider' },
        {
          kind: 'action',
          label: 'Log out',
          icon: LogOut,
          onSelect: () => {
            logout();
            navigate('/');
          },
        },
      ]}
    />
  );
}
