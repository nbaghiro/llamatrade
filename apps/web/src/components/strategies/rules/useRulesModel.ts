import { toDate } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { Strategy, StrategyVersion } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo } from 'react';

import { longestRun } from '../strategyView';

import { codeFragments } from './codeFragments';
import { ruleSentence } from './ruleSentence';
import { useRuleReadings } from './useRuleReadings';
import type { VersionTree } from './valueHistory';

/** Everything the Rules tab and the sentence panels read, from one parse of the code. */
export function useRulesModel(
  strategy: Strategy | null,
  versions: readonly StrategyVersion[],
  runs: readonly BacktestRun[]
) {
  const code = strategy?.dslCode ?? '';
  const version = strategy?.version || 1;
  const parsed = useMemo(() => (code ? fromDSLString(code) : null), [code]);
  const tree = parsed?.tree ?? null;
  const timeframe = parsed?.metadata.timeframe ?? '1D';
  const sentence = useMemo(() => (tree ? ruleSentence(tree, timeframe) : null), [tree, timeframe]);
  const fragments = useMemo(
    () => (tree ? codeFragments(code, tree) : new Map<string, string>()),
    [tree, code]
  );
  const versionTrees = useMemo<VersionTree[]>(() => {
    if (!tree) return [];
    const older = versions
      .filter((v) => v.version < version)
      .sort((a, b) => b.version - a.version)
      .flatMap((v) => {
        const p = fromDSLString(v.dslCode);
        return p ? [{ version: v.version, tree: p.tree }] : [];
      });
    return [{ version, tree }, ...older];
  }, [tree, versions, version]);

  const longest = useMemo(() => longestRun(runs, version), [runs, version]);
  const fromSec = toDate(longest?.config?.startDate)?.getTime() ?? null;
  const toSec = toDate(longest?.config?.endDate)?.getTime() ?? null;
  const window = useMemo(
    () =>
      fromSec !== null && toSec !== null ? { from: new Date(fromSec), to: new Date(toSec) } : null,
    [fromSec, toSec]
  );
  const readings = useRuleReadings(tree, timeframe, window);

  return {
    parsed,
    tree,
    timeframe,
    benchmark: parsed?.metadata.benchmark ?? '',
    sentence,
    fragments,
    versionTrees,
    readings,
    longest,
  };
}

export type RulesModel = ReturnType<typeof useRulesModel>;
