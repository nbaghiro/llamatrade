import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { ChatMessage } from '../ChatMessage';
import { DraftChoices } from '../DraftChoices';
import { draftRequest, parseDraftQuestions } from '../draftQuestions';

import { message, tool } from './helpers';

const html = (node: JSX.Element) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

const ask = `Four details change how it trades.

\`\`\`draft-questions
{"questions":[{"id":"t","label":"Which Treasuries?","short":"Treasuries","help":"Where it goes when SPY is weak.","options":["BIL","SHY","IEF"],"default":"SHY"}]}
\`\`\``;

describe('DraftChoices', () => {
  it('shows each choice with the preset checked and the actions', () => {
    const questions = parseDraftQuestions(ask)?.questions ?? [];
    const out = html(
      <DraftChoices questions={questions} onDraft={() => {}} onDefaults={() => {}} />
    );
    expect(out).toContain('Which Treasuries?');
    expect(out).toMatch(/aria-checked="true"[^>]*>SHY</);
    expect(out).toContain('Draft with these');
    expect(out).toContain('Nothing is saved or run yet');
  });

  it('keeps an answered card as a record without actions', () => {
    const questions = parseDraftQuestions(ask)?.questions ?? [];
    const out = html(
      <DraftChoices questions={questions} onDraft={() => {}} onDefaults={() => {}} answered />
    );
    expect(out).not.toContain('Draft with these');
    expect(out).toContain('Answered below');
  });
});

describe('ChatMessage', () => {
  it('reads the questions block into a card and hides the raw JSON', () => {
    const out = html(<ChatMessage message={message('a', ask)} onReply={() => {}} />);
    expect(out).toContain('Four details change how it trades.');
    expect(out).toContain('Draft with these');
    expect(out).not.toContain('"questions"');
  });

  it('shows the person their own words, not the draft instruction', () => {
    const out = html(
      <ChatMessage message={message('u', draftRequest('Hold SPY and BND'), { user: true })} />
    );
    expect(out).toContain('Hold SPY and BND');
    expect(out).not.toContain('draft-questions');
  });

  it('turns inline markers into thread-numbered citations and summarises what was read', () => {
    const calls = [tool({ name: 'get_strategy' }), tool({ name: 'get_positions', id: 'p' })];
    const out = html(
      <ChatMessage
        message={message('a', 'It holds TLT [2].', { toolCalls: calls })}
        firstSource={4}
      />
    );
    expect(out).toContain('aria-label="Source 5"');
    expect(out).toContain('Read the rule and positions');
  });
});
