import { describe, expect, it } from 'vitest';

import {
  answersMessage,
  DRAFT_INSTRUCTION,
  draftRequest,
  hideDraftBlock,
  looksLikeDraft,
  MAX_QUESTIONS,
  parseDraftQuestions,
  presetPicks,
  stripDraftInstruction,
} from '../draftQuestions';

const block = (json: string, tag = 'draft-questions') =>
  `I can draft that. Four details change how it trades.\n\n\`\`\`${tag}\n${json}\n\`\`\``;

const lookback = {
  id: 'lookback',
  label: 'How is strongest measured?',
  short: 'Strongest over',
  help: 'The return over this period ranks the ETFs.',
  options: ['3 months', '90 days', '6 months'],
  default: '90 days',
};

describe('draft requests', () => {
  it('appends the instruction and strips it back to the person’s words', () => {
    const sent = draftRequest('  Hold the three strongest sector ETFs ');
    expect(sent.endsWith(DRAFT_INSTRUCTION)).toBe(true);
    expect(stripDraftInstruction(sent)).toBe('Hold the three strongest sector ETFs');
    expect(stripDraftInstruction('Why is it frozen?')).toBe('Why is it frozen?');
  });
});

describe('parseDraftQuestions', () => {
  it('reads the questions and the text around the block', () => {
    const ask = parseDraftQuestions(block(JSON.stringify({ questions: [lookback] })));
    expect(ask?.intro).toBe('I can draft that. Four details change how it trades.');
    expect(ask?.questions).toEqual([
      {
        id: 'lookback',
        label: 'How is strongest measured?',
        short: 'Strongest over',
        help: 'The return over this period ranks the ETFs.',
        options: ['3 months', '90 days', '6 months'],
        preset: '90 days',
      },
    ]);
  });

  it('accepts a json block holding a bare list', () => {
    const ask = parseDraftQuestions(block(JSON.stringify([lookback]), 'json'));
    expect(ask?.questions).toHaveLength(1);
  });

  it('fills in the id, short label and preset when they are missing or wrong', () => {
    const ask = parseDraftQuestions(
      block(
        JSON.stringify({
          questions: [
            { label: 'Which Treasuries?', options: ['BIL', 'SHY', 'SHY'], default: 'TLT' },
          ],
        })
      )
    );
    expect(ask?.questions[0]).toMatchObject({
      id: 'q1',
      short: 'Which Treasuries?',
      options: ['BIL', 'SHY'],
      preset: 'BIL',
      help: '',
    });
  });

  it('drops questions without a label or two options and caps the count', () => {
    const many = Array.from({ length: 6 }, (_, i) => ({ ...lookback, id: `q${i}` }));
    const ask = parseDraftQuestions(
      block(
        JSON.stringify({
          questions: [
            { label: '', options: ['a', 'b'] },
            { label: 'One', options: ['a'] },
            ...many,
          ],
        })
      )
    );
    expect(ask?.questions).toHaveLength(MAX_QUESTIONS);
    expect(ask?.questions[0].id).toBe('q0');
  });

  it('returns null without a usable block', () => {
    expect(parseDraftQuestions('Here is your draft.')).toBeNull();
    expect(parseDraftQuestions(block('{not json'))).toBeNull();
    expect(parseDraftQuestions(block('{"questions": "none"}'))).toBeNull();
    expect(parseDraftQuestions(block('{"questions": [{"label": "x", "options": []}]}'))).toBeNull();
  });
});

describe('hideDraftBlock', () => {
  it('cuts a half-streamed block and leaves other text alone', () => {
    expect(hideDraftBlock('I can draft that.\n\n```draft-questions\n{"quest')).toBe(
      'I can draft that.'
    );
    expect(hideDraftBlock('Plain answer')).toBe('Plain answer');
  });
});

describe('answers', () => {
  it('starts from each preset and lists the chosen answers', () => {
    const ask = parseDraftQuestions(block(JSON.stringify({ questions: [lookback] })));
    const questions = ask?.questions ?? [];
    expect(presetPicks(questions)).toEqual({ lookback: '90 days' });
    expect(answersMessage(questions, { lookback: '6 months' })).toBe(
      'Draft it with these choices:\n- How is strongest measured? 6 months'
    );
    expect(answersMessage(questions, {})).toContain('90 days');
  });
});

describe('looksLikeDraft', () => {
  it('treats descriptions as drafts and questions as questions', () => {
    expect(looksLikeDraft('Hold the three strongest sector ETFs')).toBe(true);
    expect(looksLikeDraft('A momentum rotation across QQQ, XLK and SMH')).toBe(true);
    expect(looksLikeDraft('Why is Recession Radar in bonds and gold?')).toBe(false);
    expect(looksLikeDraft('Backtest v3 and v4 over five years')).toBe(false);
    expect(looksLikeDraft('Explain the rebalance')).toBe(false);
    expect(looksLikeDraft('Hold SPY')).toBe(false);
    expect(looksLikeDraft('Hold SPY when it is above its 200-day average?')).toBe(false);
  });
});
