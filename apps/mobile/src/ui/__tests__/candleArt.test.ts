import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { candleArt, candles, hashSeed, rng, series } from '../candleArt.ts';

describe('rng', () => {
  it('repeats for the same seed and differs across seeds', () => {
    const a = rng(7);
    const b = rng(7);
    const c = rng(8);
    const first = [a(), a(), a()];
    assert.deepEqual(first, [b(), b(), b()]);
    assert.notDeepEqual(first, [c(), c(), c()]);
    for (const v of first) assert.ok(v >= 0 && v < 1);
  });
});

describe('series', () => {
  it('starts at 1 and ends at 1 + ret', () => {
    const s = series(11, 40, 0.3, 0.02);
    assert.equal(s.length, 40);
    assert.ok(Math.abs(s[0] - 1) < 1e-9);
    assert.ok(Math.abs(s[39] - 1.3) < 1e-9);
  });

  it('handles a single point without dividing by zero', () => {
    assert.ok(series(3, 1, 0.2, 0.02).every(Number.isFinite));
  });
});

describe('candles', () => {
  it('keeps every high above and every low below its body', () => {
    for (const [o, h, l, c] of candles(5, 60, 0.4, 0.02)) {
      assert.ok(h >= Math.max(o, c));
      assert.ok(l <= Math.min(o, c));
    }
  });
});

describe('hashSeed', () => {
  it('is stable for a name and never zero', () => {
    assert.equal(hashSeed('Home'), hashSeed('Home'));
    assert.notEqual(hashSeed('Home'), hashSeed('Markets'));
    assert.equal(hashSeed(0), 1);
    assert.equal(hashSeed(''), hashSeed(''));
    assert.ok(hashSeed('') > 0);
  });
});

describe('candleArt', () => {
  it('is deterministic per seed and size', () => {
    assert.deepEqual(candleArt(42, 390, 420), candleArt(42, 390, 420));
    assert.notDeepEqual(candleArt(42, 390, 420).wicks, candleArt(43, 390, 420).wicks);
  });

  it('draws one wick per candle, about one every 12pt, and splits bodies by direction', () => {
    const art = candleArt(9, 360, 400);
    const wicks = art.wicks.match(/M/g)?.length ?? 0;
    const bodies = (art.up.match(/Z/g)?.length ?? 0) + (art.down.match(/Z/g)?.length ?? 0);
    assert.equal(wicks, 30);
    assert.equal(bodies, 30);
  });

  it('stays inside the box', () => {
    const art = candleArt(77, 390, 420);
    const ys = [...art.wicks.matchAll(/M([\d.-]+) ([\d.-]+)V([\d.-]+)/g)].flatMap((m) => [
      Number(m[2]),
      Number(m[3]),
    ]);
    assert.ok(ys.every((y) => y >= 0 && y <= 420));
  });

  it('survives a zero size', () => {
    const art = candleArt(1, 0, 0);
    assert.ok(art.wicks.length > 0);
    assert.ok(!art.wicks.includes('NaN'));
  });
});
