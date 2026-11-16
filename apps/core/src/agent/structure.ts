/** A strategy's structure as written in its DSL: rules and funds as readable outline lines. */
import { fromDSLString } from "../strategy/serializer";
import type {
  Block,
  BlockId,
  StrategyTree,
  WeightMethod,
} from "../strategy/types";

export interface OutlineLine {
  depth: number;
  kind: "rule" | "otherwise" | "weight" | "group" | "funds";
  text: string;
  /** Fund symbols on a `funds` line, with their specified weight in percent when one is set. */
  funds?: { symbol: string; weight?: number }[];
}

export interface StrategyStructure {
  name: string;
  rebalance: string;
  benchmark: string;
  /** Every distinct fund the strategy can hold, in the order written. */
  symbols: string[];
  lines: OutlineLine[];
}

const METHOD_LABEL: Record<WeightMethod, string> = {
  specified: "Fixed weights",
  equal: "Equal weight",
  inverse_volatility: "Weighted by inverse volatility",
  market_cap: "Weighted by market cap",
  momentum: "Weighted by momentum",
  min_variance: "Minimum variance weights",
  risk_parity: "Risk parity weights",
};

function weightText(block: Extract<Block, { type: "weight" }>): string {
  const parts = [METHOD_LABEL[block.method] ?? block.method];
  if (block.top) parts.push(`top ${block.top}`);
  if (block.lookbackDays) parts.push(`${block.lookbackDays}-day lookback`);
  return parts.join(", ");
}

function capitalize(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

function walk(
  tree: StrategyTree,
  ids: readonly BlockId[],
  depth: number,
  out: OutlineLine[],
) {
  const parent = ids.length
    ? tree.blocks[tree.blocks[ids[0]]?.parentId ?? ""]
    : undefined;
  const allocations =
    parent?.type === "weight" && parent.method === "specified"
      ? parent.allocations
      : {};
  let funds: NonNullable<OutlineLine["funds"]> = [];
  const flush = () => {
    if (!funds.length) return;
    out.push({
      depth,
      kind: "funds",
      text: funds.map((f) => f.symbol).join(" · "),
      funds,
    });
    funds = [];
  };

  for (const id of ids) {
    const block = tree.blocks[id];
    if (!block) continue;
    if (block.type === "asset") {
      const weight = allocations[id];
      funds.push(
        weight === undefined
          ? { symbol: block.symbol }
          : { symbol: block.symbol, weight },
      );
      continue;
    }
    flush();
    switch (block.type) {
      case "if":
        out.push({ depth, kind: "rule", text: `If ${block.conditionText}` });
        break;
      case "else":
        out.push({ depth, kind: "otherwise", text: "Otherwise" });
        break;
      case "weight":
        out.push({ depth, kind: "weight", text: weightText(block) });
        break;
      case "filter": {
        const lookback = block.config.lookbackDays
          ? `, ${block.config.lookbackDays}-day lookback`
          : block.config.period
            ? `, ${block.config.period} lookback`
            : "";
        out.push({
          depth,
          kind: "rule",
          text: `${capitalize(block.displayText)}${lookback}`,
        });
        break;
      }
      case "group":
        out.push({ depth, kind: "group", text: block.name });
        break;
      case "root":
        break;
    }
    if ("childIds" in block) walk(tree, block.childIds, depth + 1, out);
  }
  flush();
}

/** Parses the DSL into outline lines; null when the code doesn't parse. */
export function strategyStructure(dsl: string): StrategyStructure | null {
  if (!dsl.trim()) return null;
  const parsed = fromDSLString(dsl);
  if (!parsed) return null;
  const { tree, metadata } = parsed;
  const root = tree.blocks[tree.rootId];
  const lines: OutlineLine[] = [];
  if (root?.type === "root") walk(tree, root.childIds, 0, lines);

  const symbols: string[] = [];
  for (const line of lines) {
    for (const f of line.funds ?? [])
      if (!symbols.includes(f.symbol)) symbols.push(f.symbol);
  }
  return {
    name: metadata.name ?? "",
    rebalance: dsl.match(/:rebalance\s+([A-Za-z-]+)/)?.[1] ?? "",
    benchmark: metadata.benchmark ?? "",
    symbols,
    lines,
  };
}

function shares(
  tree: StrategyTree,
  id: BlockId,
  share: number,
  out: Record<string, number>,
): boolean {
  const block = tree.blocks[id];
  if (!block) return false;
  switch (block.type) {
    case "asset":
      out[block.symbol] = (out[block.symbol] ?? 0) + share;
      return true;
    case "root":
    case "group":
      return (
        block.childIds.length === 1 &&
        shares(tree, block.childIds[0], share, out)
      );
    case "weight": {
      const kids = block.childIds;
      if (!kids.length) return false;
      if (block.method === "equal" && !block.top) {
        return kids.every((k) => shares(tree, k, share / kids.length, out));
      }
      if (block.method !== "specified") return false;
      const total = kids.reduce((s, k) => s + (block.allocations[k] ?? 0), 0);
      if (total <= 0) return false;
      return kids.every((k) =>
        shares(tree, k, (share * (block.allocations[k] ?? 0)) / total, out),
      );
    }
    default:
      return false;
  }
}

/**
 * Target weight per symbol, as fractions, when the strategy's weights are fixed: only specified
 * and plain equal weights, nested through groups. Null when any rule, filter or computed weighting
 * decides what it holds.
 */
export function fixedTargets(dsl: string): Record<string, number> | null {
  if (!dsl.trim()) return null;
  const parsed = fromDSLString(dsl);
  if (!parsed) return null;
  const out: Record<string, number> = {};
  return shares(parsed.tree, parsed.tree.rootId, 1, out) &&
    Object.keys(out).length
    ? out
    : null;
}
