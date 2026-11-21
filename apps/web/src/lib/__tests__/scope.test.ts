import { describe, expect, it } from 'vitest';

import {
  alpacaAccountLabel,
  distinctMasks,
  inScope,
  maskedAccount,
  parseScope,
  resolveScope,
  scopeChoices,
} from '../scope';

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

  it('masks an account number to its last four characters', () => {
    expect(maskedAccount('PA3XK7Q04821')).toBe('••4821');
    expect(maskedAccount('pa3xk7qpa92')).toBe('••PA92');
    expect(maskedAccount('  ')).toBe('');
    expect(maskedAccount(undefined)).toBe('');
  });

  it('offers All accounts only when both kinds are connected', () => {
    const live = { isPaper: false, accountNumber: '904124821' };
    const paper = { isPaper: true, accountNumber: 'PA3XXpa92' };
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

describe('telling accounts apart', () => {
  it('leaves out a masked account number two accounts share', () => {
    expect(distinctMasks(['PA1X0050', '9011X0050', 'PA3XPA92'])).toEqual(['', '', '••PA92']);
    expect(
      scopeChoices([
        { isPaper: true, accountNumber: 'PA1X0050' },
        { isPaper: false, accountNumber: '9011X0050' },
      ]).map((c) => c.label)
    ).toEqual(['All accounts', 'Live', 'Paper']);
  });

  it('names an account by kind alone when its number is not known yet', () => {
    expect(
      scopeChoices([
        { isPaper: true, accountNumber: '' },
        { isPaper: false, accountNumber: '904124821' },
      ]).map((c) => c.label)
    ).toEqual(['All accounts', 'Live ••4821', 'Paper']);
  });

  it('labels an Alpaca account with its number when it tells the two apart', () => {
    expect(alpacaAccountLabel(true, '904124821')).toBe('Alpaca live ••4821');
    expect(alpacaAccountLabel(false, 'PA3XPA92', '904124821')).toBe('Alpaca paper ••PA92');
    expect(alpacaAccountLabel(true, '9011X0050', 'PA1X0050')).toBe('Alpaca live');
    expect(alpacaAccountLabel(false, '')).toBe('Alpaca paper');
    expect(alpacaAccountLabel(false, undefined)).toBe('Alpaca paper');
  });
});
