import { describe, expect, it } from 'vitest';

import { DIVIDER } from '../data/sections';
import { AXIS_TICK_STEP, axisTicks, dividerLabels } from '../lib/dividers';

describe('dividerLabels', () => {
  it('numbers sections from 01 in page order, lower case', () => {
    expect(dividerLabels(['The app', ' Build '])).toEqual(['01 the app', '02 build']);
  });

  it('pads to the width of the largest number', () => {
    const labels = dividerLabels(Array.from({ length: 120 }, (_, i) => `s${i}`));
    expect(labels[0]).toBe('001 s0');
    expect(labels[119]).toBe('120 s119');
  });

  it('labels the seven page sections', () => {
    expect(Object.values(DIVIDER)).toEqual([
      '01 the app',
      '02 build',
      '03 backtest',
      '04 copilot',
      '05 sessions',
      '06 your account',
      '07 invite only · paper and live',
    ]);
  });
});

describe('axisTicks', () => {
  it('starts at 0 and steps every 48px', () => {
    expect(axisTicks(200)).toEqual([0, 48, 96, 144, 192]);
    expect(AXIS_TICK_STEP).toBe(48);
  });

  it('keeps every tick inside the rule', () => {
    expect(axisTicks(97)).toEqual([0, 48, 96]);
    expect(axisTicks(96)).toEqual([0, 48]);
  });

  it('returns no ticks for an unmeasured rule or a bad step', () => {
    expect(axisTicks(0)).toEqual([]);
    expect(axisTicks(0.5)).toEqual([]);
    expect(axisTicks(100, 0)).toEqual([]);
  });

  it('honours a custom step', () => {
    expect(axisTicks(30, 10)).toEqual([0, 10, 20]);
  });
});
