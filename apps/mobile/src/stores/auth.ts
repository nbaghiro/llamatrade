/**
 * Mobile auth store: the shared core factory, persisted to the secure enclave.
 * The tenant-context accessor is exported as `tenantContext` to match the mobile
 * call sites (transport factory, per-store identity threading, streaming spike).
 */
import { createAuthStore, isTokenExpired } from '@llamatrade/core/stores/auth';

import { secureStorage } from '../net/secure-storage';

export type { AuthUser } from '@llamatrade/core/stores/auth';
export { isTokenExpired };

export const { useAuthStore, getTenantContext: tenantContext } = createAuthStore({
  storage: secureStorage,
});
