import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { citationNumbers, datedCitations, pinIndex, sourcesLabel, splitCitations, threadSources } from '../citations.ts';
import {
  answersMessage,
  blockAuthor,
  changedAnswers,
  draftRequest,
  hideDraftBlock,
  looksLikeDraft,
  parseDraftQuestions,
  presetPicks,
  stripDraftInstruction,
  valueTokens,
} from '../draftQuestions.ts';
import { draftBlocks } from '../draftBlocks.ts';
import { excerpt, highlight, hitsLabel, paragraphs, searchConversation } from '../historySearch.ts';
import { copilotLimit, isRateLimited, limitCopy } from '../limits.ts';
import { settle, sheetGeometry, stopTop } from '../sheetModel.ts';
import {
  ACCOUNT_SUBJECT,
  askPlaceholder,
  buildSubjects,
  followUps,
  subjectFor,
  subjectQuestions,
  subjectReads,
  subjectStateLabel,
  type SessionInput,
  type StrategyInput,
} from '../subjects.ts';

const SESSIONS: SessionInput[] = [
  { id: 'e-tech', strategyId: 's-tech', name: 'Tech Momentum Rotation', live: false, state: 'stopped', version: 4 },
  { id: 'e-rr', strategyId: 's-rr', name: 'Recession Radar', live: false, state: 'running', version: 3 },
  { id: 'e-ms', strategyId: 's-ms', name: 'Momentum Sectors', live: false, state: 'frozen', version: 5 },
  { id: 'e-aw', strategyId: 's-aw', name: 'All-Weather Portfolio', live: true, state: 'running', version: 2 },
];
const STRATEGIES: StrategyInput[] = [
  { id: 's-rr', name: 'Recession Radar', draft: false, version: 3, backtested: true },
  { id: 's-rp', name: 'Risk Parity', draft: false, version: 1, backtested: true },
  { id: 's-pb', name: 'Pullback Buyer', draft: true, version: 1, backtested: false },
];

describe('subjects', () => {
  const subjects = buildSubjects(SESSIONS, STRATEGIES);

  it('puts the account first, frozen before running, stopped last among sessions', () => {
    assert.deepEqual(
      subjects.map((s) => s.name),
      ['Account', 'Momentum Sectors', 'Recession Radar', 'All-Weather Portfolio', 'Tech Momentum Rotation', 'Risk Parity', 'Pullback Buyer'],
    );
  });

  it('leaves out strategies that run as a session and labels Risk Parity as never run', () => {
    const rp = subjects.find((s) => s.name === 'Risk Parity');
    assert.equal(rp?.kind, 'strategy');
    assert.equal(subjectStateLabel(rp?.state ?? 'draft'), 'Backtested, never run');
    assert.equal(subjects.filter((s) => s.name === 'Recession Radar').length, 1);
  });

  it('keeps a stopped session stopped, never paused', () => {
    const tech = subjects.find((s) => s.name === 'Tech Momentum Rotation');
    assert.equal(tech?.state, 'stopped');
    const qs = subjectQuestions(tech ?? ACCOUNT_SUBJECT).map((q) => q.text);
    assert.ok(qs.every((q) => !/resume|rebalance/i.test(q)));
    assert.ok(qs.some((q) => /while it ran/.test(q)));
  });

  it("asks about a never-run strategy's backtest, not its running", () => {
    const rp = subjects.find((s) => s.name === 'Risk Parity') ?? ACCOUNT_SUBJECT;
    const qs = subjectQuestions(rp).map((q) => q.text).join(' ');
    assert.match(qs, /backtest/);
    assert.doesNotMatch(qs, /since it started|while it ran/);
  });

  it('asks why a frozen session is frozen first', () => {
    const ms = subjects.find((s) => s.name === 'Momentum Sectors') ?? ACCOUNT_SUBJECT;
    assert.equal(subjectQuestions(ms)[0].text, 'Why is Momentum Sectors frozen?');
  });

  it('resolves contexts, with markers by session id and strategies to their open session', () => {
    assert.equal(subjectFor(null, subjects), ACCOUNT_SUBJECT);
    assert.equal(subjectFor({ kind: 'marker', id: 'e-rr', date: '2026-11-17' }, subjects).name, 'Recession Radar');
    assert.equal(subjectFor({ kind: 'strategy', id: 's-rr' }, subjects).key, 'session:e-rr');
    assert.equal(subjectFor({ kind: 'strategy', id: 's-rp' }, subjects).key, 'strategy:s-rp');
    assert.equal(subjectFor({ kind: 'session', id: 'missing' }, subjects), ACCOUNT_SUBJECT);
  });

  it('says what Copilot reads, naming the version', () => {
    const rr = subjects.find((s) => s.name === 'Recession Radar') ?? ACCOUNT_SUBJECT;
    assert.match(subjectReads(rr), /version 3/);
    assert.match(subjectReads(ACCOUNT_SUBJECT), /can’t place/);
    assert.equal(askPlaceholder(rr), 'Ask about Recession Radar');
    assert.equal(askPlaceholder(ACCOUNT_SUBJECT), 'Ask about your account');
  });

  it('offers follow-ups not already asked', () => {
    const rr = subjects.find((s) => s.name === 'Recession Radar') ?? ACCOUNT_SUBJECT;
    const first = subjectQuestions(rr)[0].text;
    const next = followUps(rr, [first.toUpperCase()]);
    assert.equal(next.length, 2);
    assert.ok(!next.includes(first));
  });
});

describe('citations', () => {
  it('splits markers, including lists, and skips markdown links', () => {
    assert.deepEqual(splitCitations('RSI was 72.4 [2]. See [docs](x) [1, 3]'), [
      { text: 'RSI was 72.4 ' },
      { n: 2 },
      { text: '. See [docs](x) ' },
      { n: 1 },
      { n: 3 },
    ]);
    assert.deepEqual(citationNumbers('a [2] b [1] c [2]'), [2, 1]);
  });

  it('places dated citations, reading yearless dates as the latest past one', () => {
    const today = new Date(2026, 10, 17);
    const out = datedCitations('It switched on Nov 5 [3]. RSI closed above 70 since Dec 30 [2]. Today it checks [4].', today);
    assert.deepEqual(
      out.map((c) => [c.n, c.at.getFullYear(), c.at.getMonth(), c.at.getDate()]),
      [
        [3, 2026, 10, 5],
        [2, 2025, 11, 30],
        [4, 2026, 10, 17],
      ],
    );
  });

  it('numbers tool calls across the thread and skips the person', () => {
    const sources = threadSources([
      { id: 'u1', user: true, tools: [] },
      { id: 'a1', user: false, tools: [{ name: 'get_strategy', success: true }, { name: 'get_positions', success: true }] },
      { id: 'a2', user: false, tools: [{ name: 'some_new_tool', success: false }] },
    ]);
    assert.deepEqual(
      sources.map((s) => [s.n, s.messageId, s.title, s.ok]),
      [
        [1, 'a1', 'Rule', true],
        [2, 'a1', 'Positions', true],
        [3, 'a2', 'Some new tool', false],
      ],
    );
    assert.equal(sourcesLabel(1), '1 source');
    assert.equal(sourcesLabel(3), '3 sources');
  });
});

describe('draft questions', () => {
  const reply = [
    'Three parts could mean more than one rule.',
    '```draft-questions',
    JSON.stringify({
      questions: [
        { id: 'etfs', label: 'Which ETFs?', options: ['VTI QQQ SMH IWM', 'Sector SPDRs'], default: 'VTI QQQ SMH IWM' },
        { id: 'ob', label: 'What counts as overbought?', options: ["SPY's 14-day RSI above 70", "SPY's 14-day RSI above 80", "SPY's 14-day RSI above 70"], default: 'nope' },
        { id: 'bad', label: 'One option only', options: ['x'] },
      ],
    }),
    '```',
  ].join('\n');

  it('reads questions, drops duplicates and unusable ones, falls back to the first option', () => {
    const ask = parseDraftQuestions(reply);
    assert.ok(ask);
    assert.equal(ask.intro, 'Three parts could mean more than one rule.');
    assert.equal(ask.questions.length, 2);
    assert.deepEqual(ask.questions[1].options, ["SPY's 14-day RSI above 70", "SPY's 14-day RSI above 80"]);
    assert.equal(ask.questions[1].preset, "SPY's 14-day RSI above 70");
  });

  it('returns null for missing or broken blocks', () => {
    assert.equal(parseDraftQuestions('No block here'), null);
    assert.equal(parseDraftQuestions('```draft-questions\n{not json\n```'), null);
    assert.equal(parseDraftQuestions('```draft-questions\n{"questions":[]}\n```'), null);
  });

  it('hides a half-written block while streaming', () => {
    assert.equal(hideDraftBlock('Two questions.\n```draft-questions\n{"quest'), 'Two questions.');
  });

  it('builds the answers message and lists changed answers', () => {
    const ask = parseDraftQuestions(reply);
    assert.ok(ask);
    const picks = { ...presetPicks(ask.questions), ob: "SPY's 14-day RSI above 80" };
    assert.equal(
      answersMessage(ask.questions, picks),
      "Draft it with these choices:\n- Which ETFs? VTI QQQ SMH IWM\n- What counts as overbought? SPY's 14-day RSI above 80",
    );
    assert.deepEqual(changedAnswers(ask.questions, picks), ["SPY's 14-day RSI above 80"]);
  });

  it('round-trips the instruction', () => {
    assert.equal(stripDraftInstruction(draftRequest('  Hold QQQ monthly ')), 'Hold QQQ monthly');
    assert.equal(stripDraftInstruction('plain'), 'plain');
  });

  it('tells descriptions from questions', () => {
    assert.ok(looksLikeDraft('Hold the strongest of a few stock ETFs, check monthly'));
    assert.ok(!looksLikeDraft('Why is Recession Radar in bonds?'));
    assert.ok(!looksLikeDraft('Explain the rule'));
    assert.ok(!looksLikeDraft('hold'));
  });

  it('marks blocks with values the person never named as Copilot’s', () => {
    const words = ['Hold the strongest of vti, qqq and SMH, monthly'];
    assert.deepEqual(valueTokens('Top 3 by 126-day return from VTI · QQQ, monthly'), ['VTI', 'QQQ', '3', '126', 'monthly']);
    assert.equal(blockAuthor('VTI · QQQ · SMH', words), 'you');
    assert.equal(blockAuthor('Rebalance monthly', words), 'you');
    assert.equal(blockAuthor('Hold SHY', words), 'copilot');
    assert.equal(blockAuthor('Top 3 by 126-day return', words), 'copilot');
    assert.equal(blockAuthor('Otherwise', words), null);
  });
});

describe('limits', () => {
  it('names outages before rate limits', () => {
    assert.equal(copilotLimit({ serviceUnavailable: true, error: 'resource_exhausted' }), 'outage');
    assert.equal(copilotLimit({ serviceUnavailable: false, error: '[resource_exhausted] slow down' }), 'rate');
    assert.equal(copilotLimit({ serviceUnavailable: false, error: 'boom' }), null);
    assert.equal(isRateLimited(null), false);
  });

  it('says a kept question stays unsent, and when the outage started', () => {
    assert.match(limitCopy('rate', null, true).body, /kept/);
    assert.doesNotMatch(limitCopy('rate', null, false).body, /kept/);
    assert.match(limitCopy('outage', new Date(2026, 10, 17, 10, 38), false).body, /^Since 10:38\./);
    for (const c of [limitCopy('rate', null, true), limitCopy('outage', null, true)]) {
      assert.doesNotMatch(c.title + c.body, /—/);
    }
  });
});

describe('history search', () => {
  const convo = {
    id: 'c1',
    title: 'Why is it frozen?',
    messages: [
      { id: 'm1', user: true, content: 'Why is Momentum Sectors frozen?' },
      { id: 'm2', user: false, content: '**Short answer.** It froze at 09:31.\n\nAlpaca shows 43 `SMH`, the ledger 31 [2].\n\n```lisp\n(SMH)\n```' },
    ],
  };

  it('cleans paragraphs', () => {
    assert.deepEqual(paragraphs(convo.messages[1].content), ['Short answer. It froze at 09:31.', 'Alpaca shows 43 SMH, the ledger 31.']);
  });

  it('finds the paragraph in replies first, then questions, then the title', () => {
    assert.deepEqual(searchConversation(convo, 'smh'), { sessionId: 'c1', messageId: 'm2', text: 'Alpaca shows 43 SMH, the ledger 31.' });
    assert.equal(searchConversation(convo, 'momentum sectors')?.messageId, 'm1');
    assert.equal(searchConversation({ ...convo, messages: [] }, 'frozen')?.messageId, '');
    assert.equal(searchConversation(convo, '  '), null);
    assert.equal(searchConversation(convo, 'xyz'), null);
  });

  it('highlights and cuts around the match', () => {
    assert.deepEqual(highlight('SMH and smh', 'smh').map((p) => p.match), [true, false, true]);
    const long = `${'a'.repeat(200)} SMH ${'b'.repeat(200)}`;
    const cut = excerpt(long, 'smh', 60);
    assert.ok(cut.startsWith('…') && cut.endsWith('…') && cut.includes('SMH'));
    assert.equal(excerpt('short', 'x'), 'short');
    assert.equal(hitsLabel(3, 'SMH'), '3 answers mention SMH');
    assert.equal(hitsLabel(1, 'SMH'), '1 answer mentions SMH');
  });
});

describe('sheet', () => {
  const g = sheetGeometry(874, 62);

  it('rests at half or full, and closes when dragged low or flung down from half', () => {
    assert.equal(stopTop('full', g), 70);
    assert.equal(settle(g.halfTop + 10, 0, g), 'half');
    assert.equal(settle(120, 0, g), 'full');
    assert.equal(settle(g.halfTop, -1, g), 'full');
    assert.equal(settle(g.halfTop + 5, 1, g), 'closed');
    assert.equal(settle(100, 1, g), 'half');
    assert.equal(settle(800, 0, g), 'closed');
  });
});

describe('draft blocks', () => {
  const lines = [
    { depth: 0, kind: 'rule' as const, text: 'If SPY is below its 200-day average' },
    { depth: 1, kind: 'funds' as const, text: 'SHY' },
    { depth: 0, kind: 'otherwise' as const, text: 'Otherwise' },
    { depth: 1, kind: 'weight' as const, text: 'Momentum, top 3, 126-day lookback' },
    { depth: 2, kind: 'funds' as const, text: 'XLK · XLE · XLF' },
    { depth: 0, kind: 'funds' as const, text: 'GLD' },
  ];

  it('groups each rule with what sits directly under it, rebalance first', () => {
    const blocks = draftBlocks(lines, { rebalance: 'weekly', benchmark: 'SPY' }, ['Hold sector ETFs, switch to SHY when SPY is below its 200-day average, weekly']);
    assert.deepEqual(
      blocks.map((b) => [b.label, b.value, b.author]),
      [
        ['Rebalance', 'Weekly, against SPY', 'you'],
        ['If SPY is below its 200-day average', 'Hold SHY', 'you'],
        ['Otherwise', 'Momentum, top 3, 126-day lookback', 'copilot'],
        ['Holds', 'Hold XLK · XLE · XLF', 'copilot'],
        ['Holds', 'Hold GLD', 'copilot'],
      ],
    );
  });

  it('skips the rebalance block when there is none', () => {
    assert.equal(draftBlocks([], { rebalance: '', benchmark: '' }, []).length, 0);
    assert.equal(draftBlocks([], { rebalance: '', benchmark: 'SPY' }, [])[0].value, 'Against SPY');
  });
});

describe('pinIndex', () => {
  const day = (d: number) => new Date(2026, 10, d, 16).getTime();
  const times = [day(3), day(4), day(5), day(6), day(10)];

  it('pins to the last point on or before the day', () => {
    assert.equal(pinIndex(times, new Date(2026, 10, 5)), 2);
    assert.equal(pinIndex(times, new Date(2026, 10, 8)), 3);
    assert.equal(pinIndex(times, new Date(2026, 10, 10)), 4);
  });

  it('returns -1 outside the series', () => {
    assert.equal(pinIndex(times, new Date(2026, 10, 1)), -1);
    assert.equal(pinIndex(times, new Date(2026, 10, 20)), -1);
    assert.equal(pinIndex([], new Date()), -1);
  });
});
