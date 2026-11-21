import { describe, expect, it } from 'vitest';

import { draftRequest } from '../draftQuestions';
import {
  conversationKinds,
  highlight,
  outcomeLabel,
  paragraphs,
  searchConversation,
} from '../historySearch';

import { message, tool } from './helpers';

const convo = {
  id: 'c1',
  title: 'Why is Momentum Sectors frozen?',
  messages: [
    message('u1', 'Tell me about SMH', { user: true }),
    message('a1', 'The session froze.\n\nAlpaca shows 43 SMH shares and the ledger 31.', {
      toolCalls: [tool({ name: 'get_positions' })],
    }),
  ],
};

describe('paragraphs', () => {
  it('splits on blank lines and drops code blocks', () => {
    expect(paragraphs('One\n\n```\ncode\n```\n\nTwo')).toEqual(['One', 'Two']);
  });

  it('strips bold, inline code and heading marks', () => {
    expect(paragraphs('## Why\n**relative** and `rsi`')).toEqual(['Why\nrelative and rsi']);
  });
});

describe('searchConversation', () => {
  it('finds the matching paragraph in a reply before the question', () => {
    expect(searchConversation(convo, 'smh')).toMatchObject({ messageId: 'a1', paragraph: 1 });
  });

  it('falls back to the title, then to nothing', () => {
    expect(searchConversation({ ...convo, messages: [] }, 'frozen')).toMatchObject({
      paragraph: -1,
    });
    expect(searchConversation(convo, 'bitcoin')).toBeNull();
    expect(searchConversation(convo, '  ')).toBeNull();
  });
});

describe('highlight', () => {
  it('marks every case-insensitive match', () => {
    expect(highlight('SMH and smh', 'smh')).toEqual([
      { text: 'SMH', match: true },
      { text: ' and ', match: false },
      { text: 'smh', match: true },
    ]);
    expect(highlight('text', '')).toEqual([{ text: 'text', match: false }]);
  });
});

describe('conversation kinds and outcome', () => {
  it('reads explained, drafts and backtests from what Copilot did', () => {
    expect(conversationKinds(convo.messages)).toEqual(['explained']);
    expect(outcomeLabel(convo.messages)).toBe('Explained · 1 source');
    const built = [
      message('a', 'Draft', {
        artifacts: ['x'],
        toolCalls: [tool({ name: 'run_backtest' }), tool({ name: 'run_backtest' })],
      }),
    ];
    expect(conversationKinds(built)).toEqual(['drafts', 'backtests']);
    expect(outcomeLabel(built)).toBe('1 draft · 2 backtests');
    expect(conversationKinds([message('a', 'Hi')])).toEqual([]);
    expect(outcomeLabel([message('a', 'Hi')])).toBe('');
  });
});

describe('paragraphs without markup', () => {
  it('drops citation markers and the draft instruction', () => {
    expect(paragraphs('Holds TLT [1] and GLD[2, 3].')).toEqual(['Holds TLT and GLD.']);
    expect(paragraphs(draftRequest('Hold SPY and BND'))).toEqual(['Hold SPY and BND']);
  });
});
