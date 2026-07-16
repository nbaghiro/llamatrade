/**
 * Artifact preview helpers — ported verbatim from
 * apps/web/src/components/agent/PendingArtifactCard.tsx (pure functions).
 */
import type { PendingArtifact } from '@llamatrade/core/proto/agent_pb';

export interface StrategyPreview {
  name?: string;
  description?: string;
  dsl_code?: string;
  symbols?: string[];
  timeframe?: string;
}

export function parsePreview(artifact: PendingArtifact): StrategyPreview | null {
  try {
    return JSON.parse(artifact.previewJson) as StrategyPreview;
  } catch {
    return null;
  }
}

/**
 * Pretty-print DSL from scratch (the agent stores the LLM's raw, often
 * inconsistently-indented text). Each nested list starts on its own line at its
 * paren depth; the list head + inline atoms/`:params` stay on that line.
 */
export function formatDSL(code: string): string {
  const tokens = code.match(/"(?:[^"\\]|\\.)*"|;[^\n]*|[()]|[^\s()]+/g);
  if (!tokens) return code.trim();

  let out = '';
  let depth = 0;
  let prevWasOpen = false;

  for (const tok of tokens) {
    if (tok === '(') {
      if (out !== '') out += '\n' + '  '.repeat(depth);
      out += '(';
      depth += 1;
      prevWasOpen = true;
    } else if (tok === ')') {
      depth = Math.max(0, depth - 1);
      out += ')';
      prevWasOpen = false;
    } else {
      out += prevWasOpen ? tok : ` ${tok}`;
      prevWasOpen = false;
    }
  }
  return out.trim();
}

/** "rebalance monthly · benchmark SPY · N assets" from the DSL + preview. */
export function buildMeta(dsl: string, preview: StrategyPreview | null): string {
  const parts: string[] = [];
  const rebalance = dsl.match(/:rebalance\s+([A-Za-z-]+)/)?.[1];
  const benchmark = dsl.match(/:benchmark\s+([A-Za-z0-9]+)/)?.[1];
  if (rebalance) parts.push(`rebalance ${rebalance}`);
  if (benchmark) parts.push(`benchmark ${benchmark}`);
  const assetCount = (dsl.match(/\(asset\b/g) || []).length || preview?.symbols?.length || 0;
  if (assetCount > 0) parts.push(`${assetCount} assets`);
  if (parts.length === 0 && preview?.timeframe) parts.push(preview.timeframe);
  return parts.join(' · ');
}
