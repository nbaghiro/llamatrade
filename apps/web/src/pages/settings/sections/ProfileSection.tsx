import { useState } from 'react';

import { Skeleton } from '../../../components/ui';
import { authClient } from '../../../services/grpc-client';
import { useAuthStore } from '../../../store/auth';
import { alpacaSignIn, displayName, monthYear } from '../model';
import { KV, ListRow, Panel } from '../parts';
import { useAccountIdentity } from '../useAccountIdentity';

function roleLabel(roles: readonly string[] | undefined): string {
  if (!roles?.length) return 'Member';
  return roles.map((r) => r.charAt(0).toUpperCase() + r.slice(1).toLowerCase()).join(', ');
}

type ResetState = 'idle' | 'sending' | 'sent' | 'failed';

export function ProfileSection() {
  const user = useAuthStore((s) => s.user);
  const identity = useAccountIdentity();
  const [reset, setReset] = useState<ResetState>('idle');

  const sendReset = () => {
    if (!user?.email) return;
    setReset('sending');
    authClient
      .requestPasswordReset({ email: user.email })
      .then(() => setReset('sent'))
      .catch(() => setReset('failed'));
  };

  const name = displayName(user);
  const alpaca = alpacaSignIn(identity.alpacaLinked);
  const resetNote =
    reset === 'sent'
      ? `Sent to ${user?.email}. The link opens a page where you choose a new password.`
      : reset === 'failed'
        ? "The reset link couldn't be sent. Please try again."
        : 'We email you a link that opens a page where you choose a new one.';

  return (
    <div className="grid items-start gap-3 lg:grid-cols-2">
      <Panel title="Profile" aside={<span className="badge">Read only for now</span>}>
        <div className="px-3.5 py-3">
          <KV label="Name">{name || 'Not set'}</KV>
          <KV label="Email">{user?.email ?? 'Not set'}</KV>
          <KV label="Workspace">
            {!identity.loaded ? (
              <Skeleton className="ml-auto h-2.5 w-16" />
            ) : (
              (identity.workspace ?? 'Not available')
            )}
          </KV>
          <KV label="Role">{roleLabel(user?.roles)}</KV>
          <KV label="Member since">
            {!identity.loaded ? (
              <Skeleton className="ml-auto h-2.5 w-16" />
            ) : identity.memberSince ? (
              monthYear(identity.memberSince)
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
        <ListRow
          title="Alpaca sign-in"
          sub={identity.loaded ? alpaca.sub : <Skeleton className="mt-1 h-2.5 w-40" />}
          end={
            !identity.loaded || !alpaca.status ? undefined : identity.alpacaLinked ? (
              <span className="inline-flex items-center gap-1.5 text-fg-2">
                <i aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-accent" />
                {alpaca.status}
              </span>
            ) : (
              <span className="badge">{alpaca.status}</span>
            )
          }
        />
      </Panel>

      <p className="m-0 text-xs text-fg-3 lg:col-span-2">
        Name and email can&apos;t be changed here yet. Editing them is planned.
      </p>
    </div>
  );
}
