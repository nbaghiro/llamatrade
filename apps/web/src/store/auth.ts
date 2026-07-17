/**
 * Web auth store: the shared core factory, persisted to `localStorage` (default).
 */
import { createAuthStore, isTokenExpired } from '@llamatrade/core/stores/auth';

export type { AuthUser, AuthState, TenantContext } from '@llamatrade/core/stores/auth';
export { isTokenExpired };

export const { useAuthStore, getTenantContext } = createAuthStore();
