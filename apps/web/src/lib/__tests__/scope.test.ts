import { describe, expect, it } from 'vitest';

import { inScope, maskedKey, parseScope, resolveScope, scopeChoices } from '../scope';

describe('account scope', () => {
  it('parses only known scopes', () => {
    expect(parseScope('live')).toBe('live');
    expect(parseScope('LIVE')).toBeNull();
    expect(parseScope(null)).toBeNull();
  });

  it('filters by kind of money', () => {
    expect(inScope('all', true)).toBe(true);
    expect(inScope('live', true)).toBe(true);
    expect(inScope('live', false)).toBe(false);
    expect(inScope('paper', false)).toBe(true);
  });

  it('masks a key to its last four characters', () => {
    expect(maskedKey('PKAB4821')).toBe('••4821');
    expect(maskedKey('  ')).toBe('');
  });

  it('offers All accounts only when both kinds are connected', () => {
    const live = { isPaper: false, keyPrefix: 'AK124821' };
    const paper = { isPaper: true, keyPrefix: 'PKXXpa92' };
    expect(scopeChoices([paper, live])).toEqual([
      { key: 'all', label: 'All accounts' },
      { key: 'live', label: 'Live ••4821' },
      { key: 'paper', label: 'Paper ••PA92' },
    ]);
    expect(scopeChoices([paper])).toEqual([{ key: 'paper', label: 'Paper ••PA92' }]);
    expect(scopeChoices([])).toEqual([]);
  });

  it('prefers the address, then memory, then the first choice', () => {
    expect(resolveScope('live', 'paper', ['all', 'live', 'paper'])).toBe('live');
    expect(resolveScope(null, 'paper', ['all', 'live', 'paper'])).toBe('paper');
    expect(resolveScope('live', null, ['paper'])).toBe('paper');
    expect(resolveScope(null, null, [])).toBe('all');
  });
});
