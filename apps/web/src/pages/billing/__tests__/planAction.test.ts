import { describe, expect, it } from 'vitest';

import { planAction } from '../planAction';

describe('plan card actions', () => {
  it('marks the current plan and never offers it', () => {
    expect(planAction('pro', 'pro', true, true)).toEqual({ kind: 'current' });
  });

  it('allows a move down to Free during the beta, since it never charges', () => {
    expect(planAction('free', 'pro', true, true)).toEqual({
      kind: 'switch',
      label: 'Switch to Free',
    });
  });

  it('holds every move up until after the beta', () => {
    expect(planAction('pro', 'free', true, true)).toEqual({
      kind: 'unavailable',
      label: 'Opens after the beta',
    });
    expect(planAction('pro', null, true, true).kind).toBe('unavailable');
  });

  it('never offers Enterprise as self-serve', () => {
    expect(planAction('enterprise', 'pro', true, true)).toEqual({
      kind: 'unavailable',
      label: 'Not available in the beta',
    });
    expect(planAction('enterprise', 'pro', false, true).kind).toBe('unavailable');
  });

  it('offers upgrades outside the beta', () => {
    expect(planAction('pro', 'free', false, true)).toEqual({
      kind: 'switch',
      label: 'Switch to Pro',
    });
  });

  it("can't switch to a plan the billing service doesn't list", () => {
    expect(planAction('free', 'pro', true, false)).toEqual({
      kind: 'unavailable',
      label: 'Not available yet',
    });
  });
});
