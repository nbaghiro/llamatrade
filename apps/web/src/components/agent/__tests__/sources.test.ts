import { describe, expect, it } from 'vitest';

import { describeSource, figure, sourcesSummary, threadSources } from '../sources';

import { message, tool } from './helpers';

describe('figure', () => {
  it('rounds decimals, groups integers and keeps text', () => {
    expect(figure('4.12345')).toBe('4.12');
    expect(figure(12000)).toBe('12,000');
    expect(figure('SPY')).toBe('SPY');
    expect(figure(undefined)).toBe('');
  });
});

describe('describeSource', () => {
  it('reads a strategy with its version, symbols and first lines of code', () => {
    const code = Array.from({ length: 10 }, (_, i) => `line ${i + 1}`).join('\n');
    const view = describeSource(
      tool({
        name: 'get_strategy',
        durationMs: 300,
        resultJson: JSON.stringify({
          name: 'Recession Radar',
          version: 4,
          status: 'active',
          symbols: ['TLT', 'GLD'],
          dsl_code: code,
        }),
      })
    );
    expect(view.title).toBe('Recession Radar, version 4');
    expect(view.rows).toContainEqual({ label: 'Symbols', value: 'TLT, GLD' });
    expect(view.code).toHaveLength(8);
    expect(view.moreLines).toBe(2);
    expect(view.seconds).toBeCloseTo(0.3);
  });

  it('lists positions with shares and value', () => {
    const view = describeSource(
      tool({
        name: 'get_positions',
        resultJson: JSON.stringify({
          positions: [{ symbol: 'TLT', qty: '42', market_value: '3797.22' }],
        }),
      })
    );
    expect(view.title).toBe('Positions, 1 holding');
    expect(view.rows[0]).toEqual({ label: 'TLT', value: '42 shares · $3797.22' });
  });

  it('says a failed call is not used and keeps its error', () => {
    const failed = describeSource(
      tool({ name: 'get_portfolio_performance', success: false, resultJson: 'Error: timeout' })
    );
    expect(failed.ok).toBe(false);
    expect(failed.note).toBe('timeout');
    const silent = describeSource(tool({ name: 'get_positions', success: false }));
    expect(silent.note).toMatch(/does not use it/);
  });

  it('falls back to a readable name and counts for unknown or list tools', () => {
    const view = describeSource(
      tool({ name: 'list_strategies', resultJson: JSON.stringify({ strategies: [{}, {}] }) })
    );
    expect(view.title).toBe('Your strategies');
    expect(view.rows).toEqual([{ label: 'Found', value: '2 items' }]);
    expect(describeSource(tool({ name: 'new_tool', resultJson: '{}' })).title).toBe('new tool');
  });

  it('treats unparseable results as failed reads', () => {
    expect(describeSource(tool({ name: 'get_strategy', resultJson: 'not json' })).rows).toEqual([]);
  });
});

describe('threadSources', () => {
  it('numbers tool calls across the thread and skips the person’s messages', () => {
    const sources = threadSources([
      message('u1', 'Why?', { user: true }),
      message('a1', 'Because', {
        toolCalls: [tool({ name: 'get_strategy' }), tool({ name: 'get_positions' })],
      }),
      message('a2', 'And', { toolCalls: [tool({ name: 'get_asset_info', durationMs: 600 })] }),
    ]);
    expect(sources.map((s) => [s.n, s.messageId])).toEqual([
      [1, 'a1'],
      [2, 'a1'],
      [3, 'a2'],
    ]);
    expect(sourcesSummary(sources)).toBe('3 tool calls · 0.6 s');
    expect(sourcesSummary(sources.slice(0, 1))).toBe('1 tool call');
  });
});
