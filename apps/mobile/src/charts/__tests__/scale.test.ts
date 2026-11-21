import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  clip,
  dateTicks,
  laneCode,
  splitWidths,
  stepPath,
  timeLinePath,
  timeRangeOf,
  valueAt,
  xAt,
} from '../scale.ts';

const DAY = 86_400_000;
const t0 = Date.UTC(2026, 10, 1);

describe('xAt', () => {
  it('places a time proportionally and clamps outside the range', () => {
    const r = { from: 0, until: 100 };
    assert.equal(xAt(50, r, 200), 100);
    assert.equal(xAt(-10, r, 200, 20), 20);
    assert.equal(xAt(150, r, 200, 20), 220);
  });

  it('puts everything at the right edge for an empty range', () => {
    assert.equal(xAt(5, { from: 3, until: 3 }, 100), 100);
  });
});

describe('timeRangeOf', () => {
  it('spans every series', () => {
    assert.deepEqual(timeRangeOf([{ t: 5, v: 1 }], [{ t: 2, v: 0 }, { t: 9, v: 0 }]), { from: 2, until: 9 });
  });

  it('is null without points', () => {
    assert.equal(timeRangeOf([], undefined), null);
  });
});

describe('clip and timeLinePath', () => {
  const pts = [
    { t: t0 + 2 * DAY, v: 2 },
    { t: t0, v: 1 },
    { t: t0 + 4 * DAY, v: NaN },
    { t: t0 + 9 * DAY, v: 3 },
  ];

  it('sorts, drops non-finite values and keeps the range', () => {
    assert.deepEqual(
      clip(pts, { from: t0, until: t0 + 5 * DAY }).map((p) => p.v),
      [1, 2],
    );
  });

  it('draws nothing with fewer than two points in range', () => {
    assert.equal(timeLinePath(pts, { from: t0 + 3 * DAY, until: t0 + 5 * DAY }, { min: 0, max: 3 }, 100, 50), '');
  });

  it('starts at the left inset', () => {
    const d = timeLinePath(pts, { from: t0, until: t0 + 9 * DAY }, { min: 1, max: 3 }, 90, 50, { left: 10, pad: 0 });
    assert.ok(d.startsWith('M10.0,50.0'));
    assert.ok(d.endsWith('L100.0,0.0'));
  });
});

describe('stepPath', () => {
  it('carries the value from before the range and runs to the end', () => {
    const d = stepPath(
      [
        { t: 0, v: 10 },
        { t: 50, v: 20 },
      ],
      { from: 25, until: 100 },
      { min: 10, max: 20 },
      75,
      10,
      { pad: 0 },
    );
    assert.equal(d, 'M0.0,10.0 H25.0 V0.0 H75.0');
  });

  it('is empty without points', () => {
    assert.equal(stepPath([], { from: 0, until: 1 }, { min: 0, max: 1 }, 10, 10), '');
  });
});

describe('valueAt', () => {
  it('takes the last value at or before the time', () => {
    const pts = [
      { t: 10, v: 1 },
      { t: 20, v: 2 },
    ];
    assert.equal(valueAt(pts, 15), 1);
    assert.equal(valueAt(pts, 20), 2);
    assert.equal(valueAt(pts, 5), null);
  });
});

describe('dateTicks', () => {
  it('labels the first and last day', () => {
    const ticks = dateTicks({ from: t0, until: t0 + 16 * DAY }, 2);
    assert.equal(ticks.length, 2);
    assert.match(ticks[0].label, /^(Oct|Nov) \d+$/);
  });

  it('uses years for long spans', () => {
    assert.match(dateTicks({ from: t0 - 400 * DAY, until: t0 }, 2)[1].label, /^\w{3} 20\d\d$/);
  });
});

describe('laneCode', () => {
  it('takes initials of the first two words', () => {
    assert.equal(laneCode('All-Weather Portfolio'), 'AW');
    assert.equal(laneCode('Recession Radar (paper)'), 'RR');
    assert.equal(laneCode('Momentum'), 'MO');
    assert.equal(laneCode(''), '?');
  });
});

describe('splitWidths', () => {
  it('shares the width after the gaps', () => {
    assert.deepEqual(splitWidths([1, 3], 103, 3), [25, 75]);
  });

  it('gives skipped segments no width and no gap', () => {
    assert.deepEqual(splitWidths([0, 2, -1], 50, 3), [0, 50, 0]);
    assert.deepEqual(splitWidths([0, 0], 50), [0, 0]);
  });
});
