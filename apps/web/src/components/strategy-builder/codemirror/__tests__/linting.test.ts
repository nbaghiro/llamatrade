import { tokenizeWithPositions } from '@llamatrade/core/strategy/serializer';
import { describe, expect, it } from 'vitest';

import { checkWeightSums } from '../linting';

/** Run the specified-weight sum check over a DSL string. */
function sums(dsl: string) {
  return checkWeightSums(tokenizeWithPositions(dsl));
}

describe('checkWeightSums', () => {
  it('passes when specified weights total 100', () => {
    expect(sums('(weight :method specified (asset SPY :weight 60) (asset QQQ :weight 40))')).toHaveLength(0);
  });

  it('flags a specified block that does not total 100', () => {
    const d = sums('(weight :method specified (asset SPY :weight 60) (asset QQQ :weight 30))');
    expect(d).toHaveLength(1);
    expect(d[0].severity).toBe('warning');
    expect(d[0].message).toContain('90');
  });

  it('allows a single child at 100', () => {
    expect(sums('(weight :method specified (asset VTI :weight 100))')).toHaveLength(0);
  });

  it('skips computed methods (equal/momentum/…)', () => {
    expect(sums('(weight :method equal (asset SPY) (asset QQQ))')).toHaveLength(0);
  });

  it('counts group children (they carry their allocation as :weight)', () => {
    expect(
      sums('(weight :method specified (group "A" :weight 70 (asset SPY)) (asset BND :weight 30))')
    ).toHaveLength(0);
    const bad = sums('(weight :method specified (group "A" :weight 70 (asset SPY)) (asset BND :weight 40))');
    expect(bad).toHaveLength(1);
    expect(bad[0].message).toContain('110');
  });

  it('scopes nested specified blocks independently', () => {
    const dsl = `(weight :method specified
      (group "Core" :weight 50
        (weight :method specified (asset SPY :weight 30) (asset QQQ :weight 70)))
      (asset BND :weight 50))`;
    expect(sums(dsl)).toHaveLength(0);
  });

  it('flags only the offending nested block', () => {
    const dsl = `(weight :method specified
      (group "Core" :weight 50
        (weight :method specified (asset SPY :weight 30) (asset QQQ :weight 60)))
      (asset BND :weight 50))`;
    const d = sums(dsl);
    expect(d).toHaveLength(1);
    expect(d[0].message).toContain('90');
  });

  it('does not flag an unclosed block mid-edit', () => {
    expect(sums('(weight :method specified (asset SPY :weight 60)')).toHaveLength(0);
  });

  it('tolerates decimal rounding (33.3 × 3 ≈ 100)', () => {
    expect(
      sums('(weight :method specified (asset A :weight 33.3) (asset B :weight 33.3) (asset C :weight 33.4))')
    ).toHaveLength(0);
  });
});
