import { describe, expect, it } from 'vitest';

import { fitFrame, PHONE_SIZE, stackLayout, windowSize } from '../lib/frame';

describe('windowSize', () => {
  it('adds the window bar and border to the app height', () => {
    expect(windowSize()).toEqual({ width: 1200, height: 760 + 34 + 2 });
    expect(windowSize(440, 450, false)).toEqual({ width: 440, height: 452 });
  });
});

describe('fitFrame', () => {
  it('scales the design to the host width and keeps the aspect', () => {
    const { scale, height } = fitFrame(600, { width: 1200, height: 800 });
    expect(scale).toBe(0.5);
    expect(height).toBe(400);
  });

  it('returns zero before the host is measured', () => {
    expect(fitFrame(0, PHONE_SIZE)).toEqual({ scale: 0, height: 0 });
    expect(fitFrame(100, { width: 0, height: 10 })).toEqual({ scale: 0, height: 0 });
  });
});

describe('stackLayout', () => {
  it('overlaps the phones with the bottom of the centre window', () => {
    const l = stackLayout(1152, false);
    expect(l.phoneTop).toBeLessThan(l.main);
    expect(l.phoneTop + l.phone).toBeGreaterThan(l.main);
    expect(l.phoneTop).toBeCloseTo(l.main - l.phone * 0.62);
  });

  it('is tall enough for every piece plus a 16px margin', () => {
    const l = stackLayout(1152, false);
    expect(l.height).toBeCloseTo(Math.max(l.main, l.phoneTop + l.phone, l.backs) + 16);
  });

  it('drops the tilted windows and widens the centre window on small screens', () => {
    const l = stackLayout(358, true);
    expect(l.backs).toBe(0);
    expect(l.main).toBeCloseTo(fitFrame(358, windowSize()).height);
    expect(l.phone).toBeCloseTo(fitFrame(358 * 0.26, PHONE_SIZE).height);
    expect(l.phoneTop).toBeCloseTo(l.main - l.phone * 0.42);
  });

  it('collapses to the margin before measuring', () => {
    expect(stackLayout(0, false).height).toBe(16 + 40);
    expect(stackLayout(0, true).height).toBe(16);
  });
});
