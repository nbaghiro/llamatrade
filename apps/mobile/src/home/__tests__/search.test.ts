import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { narrow, pushRecent, score } from '../search.ts';

const items = [
  { key: 'aw', title: 'All-Weather Portfolio', keywords: ['live'] },
  { key: 'rr', title: 'Recession Radar', keywords: ['paper', 'TLT'] },
  { key: 'pf', title: 'Portfolio' },
];

describe('search', () => {
  it('scores title starts above word starts above anywhere', () => {
    assert.equal(score(items[2], 'port'), 3);
    assert.equal(score(items[0], 'port'), 2);
    assert.equal(score(items[1], 'dar'), 1);
    assert.equal(score(items[1], 'zzz'), 0);
    assert.equal(score(items[1], '  '), 1);
  });

  it('narrows and ranks', () => {
    assert.deepEqual(
      narrow(items, 'port').map((i) => i.key),
      ['pf', 'aw'],
    );
    assert.deepEqual(
      narrow(items, 'tlt').map((i) => i.key),
      ['rr'],
    );
    assert.equal(narrow(items, '').length, 3);
  });

  it('keeps recent unique and short', () => {
    assert.deepEqual(pushRecent(['a', 'b', 'c'], 'b', 3), ['b', 'a', 'c']);
    assert.deepEqual(pushRecent(['a', 'b', 'c'], 'd', 3), ['d', 'a', 'b']);
  });
});
