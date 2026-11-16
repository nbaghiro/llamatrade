/**
 * Onboarding and first-visit setup state. Step completion is derived from real account data;
 * only what a person chose to dismiss is stored, per user, in this browser's localStorage.
 */
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export const ONBOARDING_STORAGE_KEY = 'llamatrade-onboarding';

export type SetupStepKey = 'strategy' | 'backtest' | 'connect' | 'deploy';

export const SETUP_ORDER: readonly SetupStepKey[] = ['strategy', 'backtest', 'connect', 'deploy'];

/** What the account already has. null means that read failed or hasn't arrived. */
export interface SetupFacts {
  strategyCount: number | null;
  completedBacktestCount: number | null;
  brokerConnected: boolean | null;
  sessionCount: number | null;
}

export interface SetupStep {
  key: SetupStepKey;
  done: boolean;
  /** The step to do next. Connect becomes current only once it is the only thing in the way. */
  current: boolean;
}

export interface SetupProgress {
  steps: SetupStep[];
  doneCount: number;
  /** A session has run, so Home shows the account instead of the steps. */
  complete: boolean;
  /** Every fact needed to judge the steps has loaded. */
  known: boolean;
}

export function deriveSetupSteps(facts: SetupFacts): SetupProgress {
  const done: Record<SetupStepKey, boolean> = {
    strategy: (facts.strategyCount ?? 0) > 0,
    backtest: (facts.completedBacktestCount ?? 0) > 0,
    connect: facts.brokerConnected === true,
    deploy: (facts.sessionCount ?? 0) > 0,
  };
  // A session implies the steps before it, whatever the other reads say.
  if (done.deploy) {
    done.strategy = true;
    done.connect = true;
  }

  const pending = SETUP_ORDER.filter((k) => !done[k]);
  const inOrder = pending.filter((k) => k !== 'connect');
  const blockedOnConnect = inOrder.length === 1 && inOrder[0] === 'deploy' && !done.connect;
  const current: SetupStepKey | null = blockedOnConnect
    ? 'connect'
    : (inOrder[0] ?? pending[0] ?? null);

  return {
    steps: SETUP_ORDER.map((key) => ({ key, done: done[key], current: key === current })),
    doneCount: SETUP_ORDER.filter((k) => done[k]).length,
    complete: done.deploy,
    known:
      facts.strategyCount !== null &&
      facts.completedBacktestCount !== null &&
      facts.brokerConnected !== null &&
      facts.sessionCount !== null,
  };
}

export interface UserOnboarding {
  /** The person hid the setup steps on Home. */
  setupDismissed: boolean;
  /** The person opened or skipped /welcome, so sign-in no longer sends them there. */
  welcomeSeen: boolean;
}

const BLANK: UserOnboarding = { setupDismissed: false, welcomeSeen: false };

interface OnboardingState {
  byUser: Record<string, UserOnboarding>;
  dismissSetup: (userId: string) => void;
  restoreSetup: (userId: string) => void;
  markWelcomeSeen: (userId: string) => void;
}

function sanitize(raw: unknown): Record<string, UserOnboarding> {
  if (typeof raw !== 'object' || raw === null) return {};
  const out: Record<string, UserOnboarding> = {};
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!id || typeof value !== 'object' || value === null) continue;
    const v = value as Record<string, unknown>;
    out[id] = { setupDismissed: v.setupDismissed === true, welcomeSeen: v.welcomeSeen === true };
  }
  return out;
}

/** The stored entry for a user, or the defaults when there is none. */
export function userOnboarding(
  byUser: Record<string, UserOnboarding>,
  userId: string | null | undefined
): UserOnboarding {
  return (userId && byUser[userId]) || BLANK;
}

/** Whether a fresh sign-in should land on /welcome instead of Home. */
export function shouldOpenWelcome(entry: UserOnboarding, strategyCount: number | null): boolean {
  return !entry.welcomeSeen && strategyCount === 0;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => {
      const patch = (userId: string, change: Partial<UserOnboarding>) => {
        if (!userId) return;
        set((s) => ({
          byUser: { ...s.byUser, [userId]: { ...userOnboarding(s.byUser, userId), ...change } },
        }));
      };
      return {
        byUser: {},
        dismissSetup: (userId) => patch(userId, { setupDismissed: true }),
        restoreSetup: (userId) => patch(userId, { setupDismissed: false }),
        markWelcomeSeen: (userId) => patch(userId, { welcomeSeen: true }),
      };
    },
    {
      name: ONBOARDING_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ byUser: s.byUser }),
      merge: (persisted, current) => ({
        ...current,
        byUser: sanitize((persisted as { byUser?: unknown } | undefined)?.byUser),
      }),
    }
  )
);
