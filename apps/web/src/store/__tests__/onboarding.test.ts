import { beforeEach, describe, expect, it, vi } from 'vitest';

const storage = vi.hoisted(() => {
  const data = new Map<string, string>();
  const stub = {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
    key: (i: number) => [...data.keys()][i] ?? null,
    get length() {
      return data.size;
    },
  };
  (globalThis as { localStorage?: unknown }).localStorage = stub;
  return { data };
});

import {
  ONBOARDING_STORAGE_KEY,
  deriveSetupSteps,
  shouldOpenWelcome,
  useOnboardingStore,
  userOnboarding,
  type SetupFacts,
} from '../onboarding';

const facts = (over: Partial<SetupFacts> = {}): SetupFacts => ({
  strategyCount: 0,
  completedBacktestCount: 0,
  brokerConnected: false,
  sessionCount: 0,
  ...over,
});

const done = (f: SetupFacts) =>
  Object.fromEntries(deriveSetupSteps(f).steps.map((s) => [s.key, s.done]));
const current = (f: SetupFacts) => deriveSetupSteps(f).steps.find((s) => s.current)?.key ?? null;

describe('deriveSetupSteps', () => {
  it('starts a new account on choosing a strategy, nothing done', () => {
    const p = deriveSetupSteps(facts());
    expect(p.doneCount).toBe(0);
    expect(p.complete).toBe(false);
    expect(p.known).toBe(true);
    expect(current(facts())).toBe('strategy');
    expect(p.steps.map((s) => s.key)).toEqual(['strategy', 'backtest', 'connect', 'deploy']);
  });

  it('moves to backtest once a strategy exists', () => {
    const f = facts({ strategyCount: 2 });
    expect(done(f)).toMatchObject({ strategy: true, backtest: false });
    expect(current(f)).toBe('backtest');
  });

  it('accepts Connect out of order without moving the current step', () => {
    const f = facts({ brokerConnected: true });
    expect(done(f)).toMatchObject({ strategy: false, connect: true });
    expect(current(f)).toBe('strategy');
    expect(deriveSetupSteps(f).doneCount).toBe(1);
  });

  it('makes Connect current when it is the only thing before deploying', () => {
    const f = facts({ strategyCount: 1, completedBacktestCount: 1 });
    expect(current(f)).toBe('connect');
  });

  it('makes Deploy current once connected with a backtested strategy', () => {
    const f = facts({ strategyCount: 1, completedBacktestCount: 1, brokerConnected: true });
    expect(current(f)).toBe('deploy');
    expect(deriveSetupSteps(f).doneCount).toBe(3);
  });

  it('is complete once a session exists, and a session implies a strategy and a broker', () => {
    const f = facts({ sessionCount: 1, strategyCount: 0, brokerConnected: false });
    const p = deriveSetupSteps(f);
    expect(p.complete).toBe(true);
    expect(done(f)).toMatchObject({ strategy: true, connect: true, deploy: true, backtest: false });
    expect(current(f)).toBe('backtest');
  });

  it('marks nothing current when every step is done', () => {
    const f = facts({
      sessionCount: 3,
      strategyCount: 3,
      completedBacktestCount: 1,
      brokerConnected: true,
    });
    expect(current(f)).toBeNull();
    expect(deriveSetupSteps(f).doneCount).toBe(4);
  });

  it('reports unknown when any read failed, treating missing facts as not done', () => {
    const f = facts({ brokerConnected: null, completedBacktestCount: null });
    const p = deriveSetupSteps(f);
    expect(p.known).toBe(false);
    expect(done(f)).toMatchObject({ backtest: false, connect: false });
  });
});

describe('shouldOpenWelcome', () => {
  const fresh = { setupDismissed: false, welcomeSeen: false };

  it('opens for an account with no strategy that has not seen it', () => {
    expect(shouldOpenWelcome(fresh, 0)).toBe(true);
  });

  it('stays on Home once welcome was seen, when strategies exist, or when the count failed', () => {
    expect(shouldOpenWelcome({ ...fresh, welcomeSeen: true }, 0)).toBe(false);
    expect(shouldOpenWelcome(fresh, 1)).toBe(false);
    expect(shouldOpenWelcome(fresh, null)).toBe(false);
  });
});

describe('useOnboardingStore', () => {
  beforeEach(() => {
    storage.data.clear();
    useOnboardingStore.setState({ byUser: {} });
  });

  it('keeps dismissals per user', () => {
    const s = useOnboardingStore.getState();
    s.dismissSetup('u1');
    s.markWelcomeSeen('u2');

    const { byUser } = useOnboardingStore.getState();
    expect(userOnboarding(byUser, 'u1')).toEqual({ setupDismissed: true, welcomeSeen: false });
    expect(userOnboarding(byUser, 'u2')).toEqual({ setupDismissed: false, welcomeSeen: true });
    expect(userOnboarding(byUser, 'u3')).toEqual({ setupDismissed: false, welcomeSeen: false });
  });

  it('restores the setup steps without touching the welcome flag', () => {
    const s = useOnboardingStore.getState();
    s.markWelcomeSeen('u1');
    s.dismissSetup('u1');
    s.restoreSetup('u1');
    expect(userOnboarding(useOnboardingStore.getState().byUser, 'u1')).toEqual({
      setupDismissed: false,
      welcomeSeen: true,
    });
  });

  it('ignores an empty user id', () => {
    useOnboardingStore.getState().dismissSetup('');
    expect(useOnboardingStore.getState().byUser).toEqual({});
    expect(userOnboarding({}, undefined)).toEqual({ setupDismissed: false, welcomeSeen: false });
  });

  it('persists under its own key', () => {
    useOnboardingStore.getState().dismissSetup('u1');
    const raw = storage.data.get(ONBOARDING_STORAGE_KEY);
    expect(raw).toBeDefined();
    expect(JSON.parse(raw ?? '{}').state.byUser.u1.setupDismissed).toBe(true);
  });

  it('drops malformed stored entries on rehydrate', async () => {
    storage.data.set(
      ONBOARDING_STORAGE_KEY,
      JSON.stringify({
        state: { byUser: { u1: { setupDismissed: 'yes', welcomeSeen: true }, u2: 7, '': {} } },
        version: 1,
      })
    );
    await useOnboardingStore.persist.rehydrate();
    expect(useOnboardingStore.getState().byUser).toEqual({
      u1: { setupDismissed: false, welcomeSeen: true },
    });
  });
});
