import { toDate } from '@llamatrade/core/format';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Skeleton } from '../../../components/ui';
import { authClient } from '../../../services/grpc-client';
import { useAuthStore } from '../../../store/auth';
import { displayName } from '../model';
import { KV, ListRow, Panel } from '../parts';

function roleLabel(roles: readonly string[] | undefined): string {
  if (!roles?.length) return 'Member';
  return roles.map((r) => r.charAt(0).toUpperCase() + r.slice(1).toLowerCase()).join(', ');
}

const monthYear = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });

interface AccountDates {
  memberSince: Date | null;
}

type ResetState = 'idle' | 'sending' | 'sent' | 'failed';

export function ProfileSection() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [dates, setDates] = useState<AccountDates | null>(null);
  const [reset, setReset] = useState<ResetState>('idle');

  useEffect(() => {
    let live = true;
    authClient
      .getCurrentUser({})
      .then((res) => {
        if (!live) return;
        setDates({ memberSince: toDate(res.user?.createdAt) });
      })
      .catch(() => {
        if (live) setDates({ memberSince: null });
      });
    return () => {
      live = false;
    };
  }, []);

  const sendReset = () => {
    if (!user?.email) return;
    setReset('sending');
    authClient
      .requestPasswordReset({ email: user.email })
      .then(() => setReset('sent'))
      .catch(() => setReset('failed'));
  };

  const name = displayName(user);
  const resetNote =
    reset === 'sent'
      ? `Sent to ${user?.email}. The link opens a page where you choose a new password.`
      : reset === 'failed'
        ? "The reset link couldn't be sent. Please try again."
        : 'We email you a link that opens a page where you choose a new one.';

  return (
    <div className="grid gap-3">
      <Panel title="Profile" aside={<span className="badge">Read only for now</span>}>
        <div className="px-3.5 py-3">
          <KV label="Name">{name || 'Not set'}</KV>
          <KV label="Email">{user?.email ?? 'Not set'}</KV>
          <KV label="Role">{roleLabel(user?.roles)}</KV>
          <KV label="Member since">
            {dates === null ? (
              <Skeleton className="ml-auto h-2.5 w-16" />
            ) : dates.memberSince ? (
              monthYear(dates.memberSince)
            ) : (
              'Not available'
            )}
          </KV>
        </div>
      </Panel>

      <Panel title="Security">
        <ListRow
          title="Password"
          sub={<span className={reset === 'failed' ? 'text-risk' : undefined}>{resetNote}</span>}
          end={
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={sendReset}
              disabled={!user?.email || reset === 'sending'}
            >
              {reset === 'sending'
                ? 'Sending…'
                : reset === 'sent'
                  ? 'Send again'
                  : 'Send reset link'}
            </button>
          }
        />
        <ListRow
          title="Two-factor sign-in"
          sub="Not available yet."
          end={<span className="badge">Later</span>}
        />
        <ListRow
          title="Signed-in devices"
          sub="Not available yet. Signing out ends this session only."
          end={<span className="badge">Later</span>}
        />
      </Panel>

      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <span className="text-xs text-fg-3">
          Profile changes and account deletion are handled by email during the beta.
        </span>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            logout();
            navigate('/');
          }}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
