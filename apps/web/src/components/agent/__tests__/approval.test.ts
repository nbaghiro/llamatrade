import { describe, expect, it } from 'vitest';

import { approvalRecord, changedArgs, changeMessage } from '../approval';
import { askCopilotHref } from '../entry';

const args = [
  { label: 'Strategy', value: 'Tech Momentum' },
  { label: 'From', value: '2021-11-15' },
  { label: 'Capital', value: '$25,000' },
];

describe('changedArgs', () => {
  it('keeps only values the person changed, trimmed, ignoring blanks', () => {
    expect(changedArgs(args, ['Tech Momentum', ' 2021-11-15 ', '$25,000'])).toEqual([]);
    expect(changedArgs(args, ['Tech Momentum', '2020-01-02', ''])).toEqual([
      { label: 'From', value: '2020-01-02' },
    ]);
  });
});

describe('changeMessage', () => {
  it('asks for the new values in one sentence', () => {
    expect(changeMessage([])).toBe('');
    expect(changeMessage([{ label: 'From', value: '2020-01-02' }])).toBe(
      'Run it again with From 2020-01-02 instead.'
    );
    expect(
      changeMessage([
        { label: 'From', value: 'a' },
        { label: 'To', value: 'b' },
        { label: 'Capital', value: 'c' },
      ])
    ).toBe('Run it again with From a, To b and Capital c instead.');
  });
});

describe('approvalRecord', () => {
  it('writes the answer as one line without the strategy name', () => {
    expect(approvalRecord('Run a backtest', 'approved', args)).toBe(
      'You approved: run a backtest · 2021-11-15 · $25,000'
    );
    expect(approvalRecord('Run a backtest', 'declined', [])).toBe('You declined: run a backtest');
  });
});

describe('askCopilotHref', () => {
  it('builds the link with the subject and question', () => {
    expect(askCopilotHref('')).toBe('/dashboard');
    expect(askCopilotHref(' Why? ', 'session:s1')).toBe('/dashboard?about=session%3As1&q=Why%3F');
    expect(askCopilotHref('Why?', 'session:s1', { send: true })).toBe(
      '/dashboard?about=session%3As1&q=Why%3F&send=1'
    );
    expect(askCopilotHref('  ', undefined, { send: true })).toBe('/dashboard');
  });
});
