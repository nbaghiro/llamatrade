import { listStrategies } from '../../services/strategy';
import { shouldOpenWelcome, useOnboardingStore, userOnboarding } from '../../store/onboarding';

/**
 * Where a fresh sign-in lands: /welcome for an account that has no strategy and hasn't seen
 * onboarding in this browser, Home otherwise. A failed check lands on Home.
 */
export async function landingAfterSignIn(userId: string): Promise<string> {
  const entry = userOnboarding(useOnboardingStore.getState().byUser, userId);
  if (entry.welcomeSeen) return '/dashboard';
  const count = await listStrategies({ page: 1, pageSize: 1 })
    .then((r) => r.pagination?.totalItems ?? r.strategies.length)
    .catch(() => null);
  return shouldOpenWelcome(entry, count) ? '/welcome' : '/dashboard';
}
