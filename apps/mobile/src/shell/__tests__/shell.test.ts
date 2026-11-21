import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { sessionsAttention } from '../attentionModel.ts';
import { initials, TABS } from '../tabs.ts';

describe('TABS', () => {
  it('matches the web phone bar: Home, Markets, Sessions, Strategies, Copilot', () => {
    assert.deepEqual(
      TABS.map((t) => t.title),
      ['Home', 'Markets', 'Sessions', 'Strategies', 'Copilot'],
    );
  });
});

describe('initials', () => {
  it('prefers the name, then the email, then a placeholder', () => {
    assert.equal(initials({ firstName: 'Sam', lastName: 'Rivera' }), 'SR');
    assert.equal(initials({ firstName: 'sam' }), 'S');
    assert.equal(initials({ email: 'sam.rivera@fastmail.com' }), 'SR');
    assert.equal(initials({ email: 'demo@llamatrade.ai' }), 'DE');
    assert.equal(initials(null), '?');
    assert.equal(initials({ firstName: '  ', email: '' }), '?');
  });
});

describe('sessionsAttention', () => {
  const ms = { id: 's1', name: 'Momentum Sectors' };

  it('is quiet when nothing is frozen or rejected', () => {
    const a = sessionsAttention([], [], []);
    assert.equal(a.count, 0);
    assert.equal(a.label, 'Sessions');
  });

  it('counts a sleeve seen by both reads once', () => {
    const a = sessionsAttention([ms], [ms], null);
    assert.equal(a.count, 1);
    assert.equal(a.frozen.length, 1);
    assert.equal(a.label, 'Sessions, 1 needs attention');
  });

  it('adds rejected orders and tolerates failed reads', () => {
    const a = sessionsAttention(null, [ms], [{ id: 'o1', name: 'TLT' }, { id: 'o1', name: 'TLT' }]);
    assert.equal(a.count, 2);
    assert.equal(a.label, 'Sessions, 2 need attention');
  });
});
