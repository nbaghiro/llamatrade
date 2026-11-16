import { describe, expect, it } from 'vitest';

import { noMatchSentence } from '../emptyState';

describe('noMatchSentence', () => {
  it('names the search and one filter', () => {
    expect(
      noMatchSentence({ noun: 'strategies', query: 'TLT', filters: ['Draft'], total: 6 })
    ).toBe(
      'No strategies match “TLT” with the Draft filter. Clear the search or the filters to see all 6.'
    );
  });

  it('handles a search alone', () => {
    expect(noMatchSentence({ noun: 'backtests', query: ' spy ' })).toBe(
      'No backtests match “spy”. Clear the search.'
    );
  });

  it('lists several filters', () => {
    expect(
      noMatchSentence({ noun: 'sessions', filters: ['Paused', 'Monthly', 'Paper'], total: 0 })
    ).toBe('No sessions match with the Paused, Monthly and Paper filters. Clear the filters.');
  });

  it('falls back when nothing is named', () => {
    expect(noMatchSentence({ noun: 'orders' })).toBe(
      'No orders match these filters. Clear the filters.'
    );
  });
});
