import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { areaPath, axisLabel, linePath, rangeOf, rebase, timeLabels, yFor } from '../paths.ts';

describe('rangeOf', () => {
  it('spans every series and skips non-finite values', () => {
    assert.deepEqual(rangeOf([3, 5, NaN], [1, Infinity], undefined), { min: 1, max: 5 });
  });

  it('is null when there is nothing to measure', () => {
    assert.equal(rangeOf(), null);
    assert.equal(rangeOf([], [NaN]), null);
  });
});

describe('yFor', () => {
  it('maps max to the top padding and min to the bottom padding', () => {
    const r = { min: 0, max: 10 };
    assert.equal(yFor(10, r, 100, 4), 4);
    assert.equal(yFor(0, r, 100, 4), 96);
  });

  it('centres a flat range', () => {
    assert.equal(yFor(7, { min: 7, max: 7 }, 80), 40);
  });
});

describe('linePath', () => {
  it('needs at least two finite points', () => {
    assert.equal(linePath([], 100, 50), '');
    assert.equal(linePath([1], 100, 50), '');
    assert.equal(linePath([1, NaN], 100, 50), '');
  });

  it('draws left to right across the padded width', () => {
    assert.equal(linePath([0, 10], 100, 50, 0), 'M0.0,50.0 L100.0,0.0');
  });

  it('uses a shared range when one is given', () => {
    assert.equal(linePath([5, 5], 100, 50, 0, { min: 0, max: 10 }), 'M0.0,25.0 L100.0,25.0');
  });
});

describe('areaPath', () => {
  it('closes the line down to the baseline', () => {
    assert.equal(areaPath([0, 10], 100, 50, 0), 'M0.0,50.0 L100.0,0.0 L100.0,50 L0.0,50 Z');
  });

  it('is empty without a line', () => {
    assert.equal(areaPath([1], 100, 50), '');
  });
});

describe('rebase', () => {
  it('scales a series to start at the given value', () => {
    assert.deepEqual(rebase([200, 220, 180], 100), [100, 110, 90]);
  });

  it('leaves the series alone when it cannot be rebased', () => {
    assert.deepEqual(rebase([0, 0], 100), [0, 0]);
    assert.deepEqual(rebase([5, 6], 0), [5, 6]);
    assert.deepEqual(rebase([], 100), []);
  });
});

describe('axisLabel', () => {
  it('compacts thousands and millions', () => {
    assert.equal(axisLabel(104_210), '104.2k');
    assert.equal(axisLabel(1_250_000), '1.3M');
    assert.equal(axisLabel(950), '950');
    assert.equal(axisLabel(12.34), '12.3');
    assert.equal(axisLabel(-2_500), '-2.5k');
  });
});

describe('timeLabels', () => {
  it('labels the first, middle and last times', () => {
    const day = (m: number, d: number) => new Date(2026, m, d, 12).getTime() / 1000;
    assert.deepEqual(timeLabels([day(9, 14), day(9, 20), day(9, 29), day(10, 5), day(10, 13)]), [
      'Oct 14',
      'Oct 29',
      'Nov 13',
    ]);
  });

  it('switches to month and year across more than a year', () => {
    const t = (y: number, m: number) => new Date(y, m, 1, 12).getTime() / 1000;
    assert.deepEqual(timeLabels([t(2023, 6), t(2024, 6), t(2025, 5)]), ['Jul 2023', 'Jul 2024', 'Jun 2025']);
  });

  it('is empty for fewer than two valid times', () => {
    assert.deepEqual(timeLabels([]), []);
    assert.deepEqual(timeLabels([0, NaN, 1_700_000_000]), []);
  });
});
