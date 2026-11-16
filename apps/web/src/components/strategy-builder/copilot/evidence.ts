/**
 * Backtest figures Copilot already fetched in this conversation, read from its tool results so
 * a proposal can show the runs behind it. Tool results may be JSON or a Python literal.
 */

export interface ToolCallLike {
  name: string;
  resultJson: string;
  success: boolean;
}

export interface EvidenceRun {
  backtestId: string;
  totalReturn: number | null;
  maxDrawdown: number | null;
  sharpe: number | null;
}

/** Converts a Python literal (single quotes, True/False/None) into JSON text. */
export function pythonLiteralToJson(src: string): string {
  let out = '';
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (ch === "'" || ch === '"') {
      let j = i + 1;
      let value = '';
      while (j < src.length && src[j] !== ch) {
        if (src[j] === '\\' && j + 1 < src.length) {
          const next = src[j + 1];
          value += next === 'n' ? '\n' : next === 't' ? '\t' : next;
          j += 2;
        } else {
          value += src[j];
          j++;
        }
      }
      out += JSON.stringify(value);
      i = j + 1;
      continue;
    }
    const word = /^[A-Za-z_]+/.exec(src.slice(i))?.[0];
    if (word) {
      out +=
        word === 'True' ? 'true' : word === 'False' ? 'false' : word === 'None' ? 'null' : word;
      i += word.length;
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}

export function parseToolResult(raw: string): unknown {
  if (!raw.trim()) return null;
  try {
    return JSON.parse(raw);
  } catch {
    try {
      return JSON.parse(pythonLiteralToJson(raw));
    } catch {
      return null;
    }
  }
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const toNumber = (v: unknown): number | null => {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? parseFloat(v) : NaN;
  return Number.isFinite(n) ? n : null;
};

/** Completed backtest metrics from get_backtest_results calls, in the order they ran, one per run. */
export function backtestEvidence(calls: readonly ToolCallLike[]): EvidenceRun[] {
  const out: EvidenceRun[] = [];
  const seen = new Set<string>();
  for (const call of calls) {
    if (call.name !== 'get_backtest_results' || !call.success) continue;
    const parsed = parseToolResult(call.resultJson);
    const data = isRecord(parsed) && isRecord(parsed.data) ? parsed.data : parsed;
    if (!isRecord(data) || !isRecord(data.metrics)) continue;
    const id =
      typeof data.backtest_id === 'string'
        ? data.backtest_id
        : typeof data.id === 'string'
          ? data.id
          : '';
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    out.push({
      backtestId: id,
      totalReturn: toNumber(data.metrics.total_return),
      maxDrawdown: toNumber(data.metrics.max_drawdown),
      sharpe: toNumber(data.metrics.sharpe_ratio),
    });
  }
  return out;
}

/** The strategy text inside a pending artifact's preview, or null. */
export function proposalDsl(previewJson: string): string | null {
  const parsed = parseToolResult(previewJson);
  if (!isRecord(parsed)) return null;
  const dsl = parsed.dsl_code;
  return typeof dsl === 'string' && dsl.trim() ? dsl : null;
}
