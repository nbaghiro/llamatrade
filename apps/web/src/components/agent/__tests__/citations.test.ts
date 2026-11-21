import { describe, expect, it } from 'vitest';

import { readSummary, splitCitations } from '../citations';

describe('splitCitations', () => {
  it('splits text around markers and keeps the rest', () => {
    expect(splitCitations('Holds TLT[1]. Since Nov 4 [2].')).toEqual([
      { text: 'Holds TLT' },
      { n: 1 },
      { text: '. Since Nov 4 ' },
      { n: 2 },
      { text: '.' },
    ]);
  });

  it('reads a list of markers as separate citations', () => {
    expect(splitCitations('Both[1, 3]')).toEqual([{ text: 'Both' }, { n: 1 }, { n: 3 }]);
  });

  it('leaves markdown links and plain text alone', () => {
    expect(splitCitations('See [2](/x) here')).toEqual([{ text: 'See [2](/x) here' }]);
    expect(splitCitations('No markers')).toEqual([{ text: 'No markers' }]);
    expect(splitCitations('')).toEqual([]);
  });
});

describe('readSummary', () => {
  it('names each kind of record once, joined in prose', () => {
    expect(
      readSummary(['get_strategy', 'get_positions', 'get_positions', 'get_portfolio_performance'])
    ).toBe('Read the rule, positions and performance');
    expect(readSummary(['get_positions'])).toBe('Read positions');
    expect(readSummary(['some_new_tool'])).toBe('Read some new tool');
    expect(readSummary([])).toBe('');
  });
});
