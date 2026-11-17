import { describe, expect, it } from 'vitest';

import {
  COPILOT_RESULT_ID,
  copilotUrl,
  flattenGroups,
  highlightRuns,
  matchText,
  moveActive,
  parseQuery,
  pushRecent,
  rankPalette,
  type PaletteItem,
} from '../palette';

const lastOf = <T>(xs: T[]): T => xs[xs.length - 1];

const ITEMS: PaletteItem[] = [
  { id: 's:rr', kind: 'strategy', label: 'Recession Radar' },
  { id: 's:rr2', kind: 'strategy', label: 'Recession Radar v2' },
  { id: 's:60', kind: 'strategy', label: 'Classic 60/40' },
  { id: 's:mom', kind: 'strategy', label: 'Momentum Sectors' },
  { id: 'p:home', kind: 'page', label: 'Home', keywords: ['dashboard'] },
  { id: 'p:portfolio', kind: 'page', label: 'Portfolio' },
  { id: 'p:rec', kind: 'page', label: 'Portfolio › Reconciliation' },
  { id: 'a:new', kind: 'action', label: 'New strategy', keywords: ['create'] },
  { id: 'a:funds', kind: 'action', label: 'Add paper funds', keywords: ['deposit', 'wallet'] },
];

const score = (text: string, q: string) => matchText(text, q)?.score ?? -Infinity;

describe('matchText', () => {
  it('ranks exact over prefix over word start over substring over subsequence', () => {
    const exact = score('Home', 'home');
    const prefix = score('Homework', 'home');
    const word = score('Go Home', 'home');
    const sub = score('Shome', 'home');
    const seq = score('Hold my enter', 'home');
    expect(exact).toBeGreaterThan(prefix);
    expect(prefix).toBeGreaterThan(word);
    expect(word).toBeGreaterThan(sub);
    expect(sub).toBeGreaterThan(seq);
  });

  it('returns null when letters are missing', () => {
    expect(matchText('Portfolio', 'xyz')).toBeNull();
  });

  it('rejects scattered subsequences', () => {
    expect(matchText('Momentum Sectors', 'mtsr')).toBeNull();
  });

  it('reports the matched range', () => {
    expect(matchText('Recession Radar', 'rad')?.ranges).toEqual([[10, 13]]);
  });
});

describe('rankPalette', () => {
  it('drops subsequence matches when any item matches directly', () => {
    const ids = flattenGroups(rankPalette('io', ITEMS)).map((r) => r.id);
    expect(ids).toEqual(['s:rr', 's:rr2', 'p:portfolio', 'p:rec', COPILOT_RESULT_ID]);
    expect(flattenGroups(rankPalette('cl', ITEMS)).map((r) => r.id)).toEqual([
      's:60',
      COPILOT_RESULT_ID,
    ]);
  });

  it('starts a subsequence match at a word start', () => {
    const ids = flattenGroups(rankPalette('ri', ITEMS)).map((r) => r.id);
    expect(ids).toEqual(['s:rr', 's:rr2', 'p:rec', COPILOT_RESULT_ID]);
  });

  it('groups strategies, pages, actions and ends with Ask Copilot', () => {
    const groups = rankPalette('rec', ITEMS);
    expect(groups.map((g) => g.kind)).toEqual(['strategy', 'page', 'copilot']);
    expect(groups[0].results.map((r) => r.id)).toEqual(['s:rr', 's:rr2']);
    expect(groups[1].results.map((r) => r.id)).toEqual(['p:rec']);
    const last = lastOf(flattenGroups(groups));
    expect(last.id).toBe(COPILOT_RESULT_ID);
    expect(last.label).toBe('Ask Copilot about “rec”');
  });

  it('finds items by keyword', () => {
    const ids = flattenGroups(rankPalette('deposit', ITEMS)).map((r) => r.id);
    expect(ids).toEqual(['a:funds', COPILOT_RESULT_ID]);
    expect(flattenGroups(rankPalette('dashboard', ITEMS))[0].id).toBe('p:home');
  });

  it('only offers Copilot when nothing matches', () => {
    expect(flattenGroups(rankPalette('zzzz', ITEMS)).map((r) => r.id)).toEqual([COPILOT_RESULT_ID]);
  });

  it('shows the empty-query list in the given order without Copilot', () => {
    const groups = rankPalette('  ', ITEMS, {
      emptyIds: ['a:new', 'p:portfolio', 'p:home', 'missing'],
    });
    expect(groups.map((g) => g.kind)).toEqual(['page', 'action']);
    expect(groups[0].results.map((r) => r.id)).toEqual(['p:portfolio', 'p:home']);
  });

  it('caps each group', () => {
    const many: PaletteItem[] = Array.from({ length: 9 }, (_, i) => ({
      id: `s${i}`,
      kind: 'strategy',
      label: `Strategy ${i}`,
    }));
    expect(rankPalette('strategy', many, { perGroup: 3 })[0].results).toHaveLength(3);
  });

  it('keeps the typed casing in the Copilot row and collapses spaces for matching', () => {
    const groups = rankPalette('  Recession   radar ', ITEMS);
    expect(groups[0].results[0].id).toBe('s:rr');
    expect(lastOf(flattenGroups(groups)).label).toBe('Ask Copilot about “Recession   radar”');
  });
});

describe('moveActive', () => {
  it('wraps both ways', () => {
    expect(moveActive(0, -1, 4)).toBe(3);
    expect(moveActive(3, 1, 4)).toBe(0);
    expect(moveActive(1, 1, 4)).toBe(2);
    expect(moveActive(0, 1, 0)).toBe(0);
  });
});

describe('highlightRuns', () => {
  it('splits a label around matched ranges', () => {
    expect(highlightRuns('Recession Radar', [[0, 3]])).toEqual([
      { text: 'Rec', hit: true },
      { text: 'ession Radar', hit: false },
    ]);
    expect(highlightRuns('abc', [])).toEqual([{ text: 'abc', hit: false }]);
  });

  it('handles unsorted and overlapping ranges', () => {
    expect(
      highlightRuns('abcdef', [
        [3, 5],
        [0, 4],
      ])
    ).toEqual([
      { text: 'abcd', hit: true },
      { text: 'e', hit: true },
      { text: 'f', hit: false },
    ]);
  });
});

describe('copilotUrl', () => {
  it('encodes the query', () => {
    expect(copilotUrl(' why is radar frozen? ')).toBe('/copilot?q=why%20is%20radar%20frozen%3F');
    expect(copilotUrl('')).toBe('/copilot');
  });
});

describe('palette before typing', () => {
  it('groups today, sessions and recent ahead of everything else', () => {
    const items: PaletteItem[] = [
      ...ITEMS,
      { id: 't:fills', kind: 'today', label: '3 fills this morning' },
      { id: 'x:rr', kind: 'session', label: 'Recession Radar' },
      { id: 'r:bt', kind: 'recent', label: 'Risk Parity, backtest' },
    ];
    const groups = rankPalette('', items, { emptyIds: ['r:bt', 'x:rr', 't:fills', 'a:new'] });
    expect(groups.map((g) => g.title)).toEqual(['Today', 'Sessions', 'Recent', 'Actions']);
  });

  it('reads a leading > as actions only', () => {
    expect(parseQuery('> new')).toEqual({ actionsOnly: true, query: ' new' });
    expect(parseQuery('radar')).toEqual({ actionsOnly: false, query: 'radar' });
  });

  it('keeps recent entries unique, newest first, up to the limit', () => {
    const e = (id: string, at: number) => ({ id, label: id, to: `/${id}`, at });
    const list = pushRecent([e('a', 1), e('b', 2)], e('a', 3), 2);
    expect(list.map((x) => x.id)).toEqual(['a', 'b']);
    expect(pushRecent(list, e('c', 4), 2).map((x) => x.id)).toEqual(['c', 'a']);
  });
});
