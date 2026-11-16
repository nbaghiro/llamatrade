/** Reads a proposed Copilot action into the labelled arguments and plain effect shown on its approval card. */

export interface ConfirmationView {
  title: string;
  args: { label: string; value: string }[];
  /** One sentence on what the action will and won't do. */
  effect: string;
}

interface ToolCopy {
  title: string;
  effect: string;
  labels: Record<string, string>;
}

const TOOLS: Record<string, ToolCopy> = {
  run_backtest: {
    title: "Run a backtest",
    effect:
      "A backtest uses historical data only. It doesn't place orders or change the strategy.",
    labels: {
      strategy_id: "Strategy",
      dsl_code: "Strategy",
      start_date: "From",
      end_date: "To",
      initial_capital: "Capital",
    },
  },
};

const GENERIC_EFFECT =
  "Copilot runs this once you approve it, with exactly these arguments.";

const MONEY_KEYS = new Set(["initial_capital", "capital", "amount"]);

function humanize(key: string): string {
  const text = key.replace(/_/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : key;
}

function formatValue(
  key: string,
  value: unknown,
  names: Readonly<Record<string, string>>,
): string {
  if (key === "strategy_id" && typeof value === "string") {
    return names[value] ? `${names[value]}` : value;
  }
  if (key === "dsl_code" && typeof value === "string") {
    const lines = value.trim().split("\n").length;
    return `The draft in this conversation (${lines} ${lines === 1 ? "line" : "lines"})`;
  }
  if (MONEY_KEYS.has(key)) {
    const n = typeof value === "number" ? value : Number(value);
    if (Number.isFinite(n)) {
      return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
    }
  }
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  return JSON.stringify(value);
}

/**
 * Builds the approval card's content from the tool name and its JSON arguments. Unparseable
 * arguments are shown raw rather than hidden, so the person always sees what will run.
 */
export function describeConfirmation(
  toolName: string,
  argumentsJson: string,
  strategyNames: Readonly<Record<string, string>> = {},
): ConfirmationView {
  const copy = TOOLS[toolName];
  const title = copy?.title ?? humanize(toolName);
  const effect = copy?.effect ?? GENERIC_EFFECT;

  let parsed: unknown;
  try {
    parsed = JSON.parse(argumentsJson || "{}");
  } catch {
    return {
      title,
      effect,
      args: [{ label: "Arguments", value: argumentsJson }],
    };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return {
      title,
      effect,
      args: [{ label: "Arguments", value: argumentsJson }],
    };
  }

  const args = Object.entries(parsed as Record<string, unknown>)
    .filter(([, v]) => v !== "" && v !== null && v !== undefined)
    .map(([key, value]) => ({
      label: copy?.labels[key] ?? humanize(key),
      value: formatValue(key, value, strategyNames),
    }));
  return { title, effect, args };
}
