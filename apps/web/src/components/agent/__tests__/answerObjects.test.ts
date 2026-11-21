import { describe, expect, it } from 'vitest';

import { answerObjects, objectText, resultPicture } from '../answerObjects';
import { followUpsFor } from '../followUps';
import type { CopilotSubject } from '../subjects';

import { message, tool } from './helpers';

const positions = tool({
  name: 'get_positions',
  resultJson: JSON.stringify({
    positions: [
      { symbol: 'GLD', quantity: '9', market_value: '2000' },
      { symbol: 'TLT', quantity: '42', market_value: '3000' },
      { symbol: 'CASH', quantity: '0', market_value: '10' },
    ],
  }),
});
const strategy = tool({
  name: 'get_strategy',
  resultJson: JSON.stringify({
    id: 'st1',
    name: 'Momentum Sectors',
    version: 5,
    status: 'ACTIVE',
    symbols: ['XLK', 'SMH'],
  }),
});

describe('answerObjects', () => {
  it('draws positions with weights and a strategy with its link, numbered from the first source', () => {
    const objects = answerObjects(message('a', 'x', { toolCalls: [positions, strategy] }), 3);
    expect(objects[0]).toMatchObject({ kind: 'holdings', n: 3, more: 0 });
    if (objects[0].kind !== 'holdings') throw new Error('expected holdings');
    expect(objects[0].rows.map((r) => [r.symbol, r.weight])).toEqual([
      ['TLT', 0.6],
      ['GLD', 0.4],
    ]);
    expect(objects[1]).toMatchObject({
      kind: 'strategy',
      n: 4,
      name: 'Momentum Sectors',
      version: '5',
      status: 'active',
      href: '/strategies/st1',
    });
    expect(objectText(objects[1])).toContain('SMH');
  });

  it('skips failed calls, unreadable results and the person’s messages', () => {
    expect(
      answerObjects(
        message('a', 'x', { toolCalls: [tool({ name: 'get_positions', success: false })] })
      )
    ).toEqual([]);
    expect(
      answerObjects(
        message('a', 'x', { toolCalls: [tool({ name: 'get_strategy', resultJson: 'nope' })] })
      )
    ).toEqual([]);
    expect(answerObjects(message('u', 'x', { user: true, toolCalls: [positions] }))).toEqual([]);
  });
});

describe('resultPicture', () => {
  it('uses the latest holdings or symbols the conversation read', () => {
    expect(resultPicture([message('a', 'x', { toolCalls: [positions, strategy] })])).toEqual({
      kind: 'symbols',
      symbols: ['XLK', 'SMH'],
    });
    expect(resultPicture([message('a', 'x', { toolCalls: [positions] })]).kind).toBe('holdings');
    expect(resultPicture([message('a', 'Hi')])).toEqual({ kind: 'none' });
  });
});

describe('followUpsFor', () => {
  const subject = { kind: 'strategy', name: 'Risk Parity', id: 'st1' } as CopilotSubject;

  it('offers questions about the subject that weren’t asked yet', () => {
    const asked = message('u', 'Explain how Risk Parity decides what to hold', { user: true });
    expect(followUpsFor(subject, [asked])).toEqual([
      'Backtest Risk Parity over the last five years',
      'What would have hurt Risk Parity most in 2022?',
    ]);
    expect(followUpsFor(null, [asked])).toEqual([]);
  });
});
