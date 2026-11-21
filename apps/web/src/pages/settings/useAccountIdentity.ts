import { toDate } from '@llamatrade/core/format';
import { useEffect, useState } from 'react';

import { authClient } from '../../services/grpc-client';
import { useAuthStore } from '../../store/auth';

export interface AccountIdentity {
  /** The tenant's name, or null when it couldn't be read. */
  workspace: string | null;
  memberSince: Date | null;
  /** Whether the user can sign in with Alpaca; null when the user couldn't be read. */
  alpacaLinked: boolean | null;
  loaded: boolean;
}

const EMPTY: AccountIdentity = {
  workspace: null,
  memberSince: null,
  alpacaLinked: null,
  loaded: false,
};

/** One request per signed-in user and tenant, shared by every caller. */
const cache = new Map<string, Promise<AccountIdentity>>();

function load(userId: string, tenantId: string): Promise<AccountIdentity> {
  const key = `${userId}:${tenantId}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const request = Promise.all([
    authClient
      .getCurrentUser({})
      .then((r) => r.user ?? null)
      .catch(() => null),
    tenantId
      ? authClient
          .getTenant({ tenantId })
          .then((r) => r.tenant?.name.trim() || null)
          .catch(() => null)
      : Promise.resolve(null),
  ]).then(([user, workspace]) => {
    // A failed read is asked again next time rather than remembered.
    if (user === null || workspace === null) cache.delete(key);
    return {
      workspace,
      memberSince: toDate(user?.createdAt),
      alpacaLinked: user ? user.alpacaLinked : null,
      loaded: true,
    };
  });
  cache.set(key, request);
  return request;
}

/** The workspace name and member-since date for the settings header and profile. */
export function useAccountIdentity(): AccountIdentity {
  const userId = useAuthStore((s) => s.user?.id ?? '');
  const tenantId = useAuthStore((s) => s.user?.tenantId ?? '');
  const [identity, setIdentity] = useState<AccountIdentity>(EMPTY);

  useEffect(() => {
    if (!userId) return;
    let live = true;
    load(userId, tenantId)
      .then((next) => {
        if (live) setIdentity(next);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [userId, tenantId]);

  return identity;
}
