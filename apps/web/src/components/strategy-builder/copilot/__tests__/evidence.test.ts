import { describe, expect, it } from 'vitest';

import { backtestEvidence, parseToolResult, proposalDsl, pythonLiteralToJson } from '../evidence';

const PY =
  "{'success': True, 'data': {'backtest_id': 'b1', 'status': 'completed', 'note': \"Couldn't hurt\", 'metrics': {'total_return': '0.214', 'max_drawdown': '-0.123', 'sharpe_ratio': '0.79', 'alpha': None}}, 'duration_ms': 12}";

describe('pythonLiteralToJson', () => {
  it('turns a Python dict into JSON, keeping apostrophes inside strings', () => {
    const parsed = JSON.parse(pythonLiteralToJson(PY));
    expect(parsed.success).toBe(true);
    expect(parsed.data.note).toBe("Couldn't hurt");
    expect(parsed.data.metrics.alpha).toBeNull();
  });

  it('keeps escapes', () => {
    expect(JSON.parse(pythonLiteralToJson("{'a': 'x\\'y'}"))).toEqual({ a: "x'y" });
  });
});

describe('parseToolResult', () => {
  it('reads JSON and Python literals, and gives null for anything else', () => {
    expect(parseToolResult('{"a": 1}')).toEqual({ a: 1 });
    expect(parseToolResult("{'a': False}")).toEqual({ a: false });
    expect(parseToolResult('')).toBeNull();
    expect(parseToolResult('{not closed')).toBeNull();
  });
});

describe('backtestEvidence', () => {
  it('collects metrics from backtest result calls only', () => {
    const runs = backtestEvidence([
      { name: 'get_backtest_results', success: true, resultJson: PY },
      {
        name: 'run_backtest',
        success: true,
        resultJson: "{'success': True, 'data': {'backtest_id': 'b2'}}",
      },
      { name: 'get_backtest_results', success: false, resultJson: PY },
    ]);
    expect(runs).toEqual([
      { backtestId: 'b1', totalReturn: 0.214, maxDrawdown: -0.123, sharpe: 0.79 },
    ]);
  });

  it('counts a run once when it was fetched twice', () => {
    const call = { name: 'get_backtest_results', success: true, resultJson: PY };
    expect(backtestEvidence([call, call])).toHaveLength(1);
  });

  it('skips results without metrics or that do not parse', () => {
    expect(
      backtestEvidence([
        {
          name: 'get_backtest_results',
          success: true,
          resultJson: "{'success': True, 'data': {'id': 'x'}}",
        },
        { name: 'get_backtest_results', success: true, resultJson: 'nonsense' },
      ])
    ).toEqual([]);
  });

  it('leaves a missing figure as null', () => {
    const [run] = backtestEvidence([
      {
        name: 'get_backtest_results',
        success: true,
        resultJson: JSON.stringify({
          data: { id: 'b3', metrics: { total_return: '0.1', sharpe_ratio: 'nan' } },
        }),
      },
    ]);
    expect(run).toEqual({ backtestId: 'b3', totalReturn: 0.1, maxDrawdown: null, sharpe: null });
  });
});

describe('proposalDsl', () => {
  it('reads the strategy text from an artifact preview', () => {
    expect(proposalDsl(JSON.stringify({ dsl_code: '(strategy "x")' }))).toBe('(strategy "x")');
    expect(proposalDsl(JSON.stringify({ dsl_code: '  ' }))).toBeNull();
    expect(proposalDsl('{}')).toBeNull();
    expect(proposalDsl('broken')).toBeNull();
  });
});
