import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { dayLabel, hm, longDate, openLabel, shortDate } from '../when.ts';

const NOW = new Date(2026, 10, 17, 10, 42).getTime();

describe('when', () => {
  it('formats times and dates', () => {
    assert.equal(hm(new Date(2026, 10, 17, 9, 5).getTime()), '09:05');
    assert.equal(shortDate(NOW), 'Nov 17');
    assert.equal(longDate(NOW), 'Tuesday, November 17');
  });

  it('names nearby days', () => {
    assert.equal(dayLabel(new Date(2026, 10, 17, 23).getTime(), NOW), 'Today');
    assert.equal(dayLabel(new Date(2026, 10, 18).getTime(), NOW), 'Tomorrow');
    assert.equal(dayLabel(new Date(2026, 10, 16).getTime(), NOW), 'Yesterday');
    assert.equal(dayLabel(new Date(2026, 10, 20).getTime(), NOW), 'Fri');
    assert.equal(dayLabel(new Date(2026, 10, 30).getTime(), NOW), 'Nov 30');
  });

  it('labels the next open', () => {
    assert.equal(openLabel(new Date(2026, 10, 18, 9, 30).getTime(), NOW), 'Tomorrow 09:30');
  });
});
