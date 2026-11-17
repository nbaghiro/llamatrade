import { describe, expect, it } from 'vitest';

import { planAction } from '../planAction';

describe('plan card actions', () => {
  it('marks the current plan and never offers it', () => {
    expect(planAction('pro', 'pro', true)).toEqual({ kind: 'current' });
  });

  it('offers a switch up or down between self-serve plans', () => {
    expect(planAction('pro', 'free', true)).toEqual({ kind: 'switch', label: 'Switch to Pro' });
    expect(planAction('free', 'pro', true)).toEqual({ kind: 'switch', label: 'Switch to Free' });
    expect(planAction('pro', null, true).kind).toBe('switch');
  });

  it('never offers Enterprise as self-serve', () => {
    expect(planAction('enterprise', 'pro', true)).toEqual({
      kind: 'unavailable',
      label: 'Not self-serve yet',
    });
  });

  it("can't switch to a plan the billing service doesn't list", () => {
    expect(planAction('free', 'pro', false)).toEqual({
      kind: 'unavailable',
      label: 'Not available yet',
    });
  });
});
