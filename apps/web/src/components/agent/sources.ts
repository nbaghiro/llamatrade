import { MessageRole, type AgentMessage } from '@llamatrade/core/stores/agent';

/** One labelled figure a tool returned. */
export interface SourceRow {
  label: string;
  value: string;
}

/** What one tool call read, in a form the sources pane can show. */
export interface SourceView {
  /** The citation number, counted across the whole thread. */
  n: number;
  id: string;
  messageId: string;
  tool: string;
  title: string;
  rows: SourceRow[];
  /** Strategy code the call returned, trimmed to its first lines. */
  code: string[];
  /** Lines of code left out of `code`. */
  moreLines: number;
  note: string;
  seconds: number | null;
  ok: boolean;
}

type ToolCall = AgentMessage['toolCalls'][number];
type Json = Record<string, unknown>;

const CODE_LINES = 8;

const TITLES: Record<string, string> = {
  get_strategy: 'Strategy',
  list_strategies: 'Your strategies',
  list_templates: 'Templates',
  get_backtest_results: 'Backtest result',
  list_backtests: 'Backtests',
  run_backtest: 'Backtest run',
  get_portfolio_summary: 'Portfolio summary',
  get_portfolio_performance: 'Portfolio performance',
  get_positions: 'Positions',
  validate_dsl: 'Strategy check',
  get_asset_info: 'Asset',
  recall_memory: 'Earlier conversations',
  get_user_profile: 'Your profile',
  search_past_strategies: 'Past strategies',
};

function parse(raw: string): Json | null {
  if (!raw.trim()) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return value && typeof value === 'object' && !Array.isArray(value) ? (value as Json) : null;
  } catch {
    return null;
  }
}

const str = (v: unknown): string =>
  typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';

const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

/** A reported figure, rounded to two places when it is a plain number. */
export function figure(v: unknown): string {
  const text = str(v).trim();
  if (!text) return '';
  const n = Number(text);
  if (!Number.isFinite(n)) return text;
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(2);
}

function rows(entries: [string, unknown][]): SourceRow[] {
  return entries.map(([label, v]) => ({ label, value: figure(v) })).filter((r) => r.value !== '');
}

function count(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;
}

function describe(
  name: string,
  args: Json,
  data: Json
): Pick<SourceView, 'title' | 'rows' | 'note'> & { code?: string } {
  const base = TITLES[name] ?? name.replace(/_/g, ' ');
  switch (name) {
    case 'get_strategy': {
      const version = str(data.version);
      const title = [str(data.name) || base, version && `version ${version}`]
        .filter(Boolean)
        .join(', ');
      const symbols = list(data.symbols).map(str).filter(Boolean);
      return {
        title,
        rows: rows([
          ['Status', data.status],
          ['Symbols', symbols.join(', ')],
        ]),
        note: '',
        code: str(data.dsl_code),
      };
    }
    case 'get_portfolio_performance':
      return {
        title: `${base}${str(data.period) ? `, ${str(data.period)}` : ''}`,
        rows: rows([
          ['Total return', data.total_return],
          ['Benchmark return', data.benchmark_return],
          ['Max drawdown', data.max_drawdown],
          ['Sharpe ratio', data.sharpe_ratio],
          ['Positions', data.total_positions],
        ]),
        note: 'Figures as the portfolio service reported them.',
      };
    case 'get_positions': {
      const positions = list(data.positions).map((p) => (p && typeof p === 'object' ? p : {}));
      return {
        title: `${base}, ${count(positions.length, 'holding')}`,
        rows: positions.slice(0, 6).map((p) => {
          const row = p as Json;
          const qty = figure(row.qty ?? row.quantity);
          const value = figure(row.market_value);
          return {
            label: str(row.symbol) || 'Position',
            value: [qty && `${qty} shares`, value && `$${value}`].filter(Boolean).join(' · '),
          };
        }),
        note: str(data.note),
      };
    }
    case 'get_backtest_results': {
      const metrics = (
        data.metrics && typeof data.metrics === 'object' ? data.metrics : {}
      ) as Json;
      return {
        title: str(data.status) ? `${base}, ${str(data.status).toLowerCase()}` : base,
        rows: rows([
          ['Total return', metrics.total_return],
          ['Benchmark', data.benchmark_symbol],
          ['Benchmark return', metrics.benchmark_return],
          ['Max drawdown', metrics.max_drawdown],
          ['Sharpe ratio', metrics.sharpe_ratio],
          ['Trades', metrics.total_trades],
        ]),
        note: str(data.note),
      };
    }
    case 'run_backtest':
      return {
        title: base,
        rows: rows([
          ['From', args.start_date],
          ['To', args.end_date],
          ['Status', data.status],
        ]),
        note: str(data.message ?? data.note),
      };
    case 'get_asset_info':
      return {
        title: str(data.symbol ?? args.symbol) || base,
        rows: rows([
          ['Name', data.name],
          ['Exchange', data.exchange],
          ['Class', data.asset_class ?? data.class],
        ]),
        note: str(data.note),
      };
    case 'validate_dsl': {
      const errors = list(data.errors).map(str).filter(Boolean);
      return {
        title: base,
        rows: [{ label: 'Result', value: data.valid === false ? 'Has problems' : 'Valid' }],
        note: errors.slice(0, 3).join(' '),
      };
    }
    default: {
      const items =
        list(data.strategies).length ||
        list(data.backtests).length ||
        list(data.templates).length ||
        list(data.facts).length;
      return {
        title: base,
        rows: items ? [{ label: 'Found', value: count(items, 'item') }] : [],
        note: str(data.note),
      };
    }
  }
}

/** Reads one tool call into the title, figures and code the sources pane shows. */
export function describeSource(tc: ToolCall): Omit<SourceView, 'n' | 'messageId'> {
  const args = parse(tc.argumentsJson) ?? {};
  const data = parse(tc.resultJson);
  const seconds = tc.durationMs > 0 ? tc.durationMs / 1000 : null;
  if (!tc.success || !data) {
    const error = tc.resultJson.replace(/^Error:\s*/, '').trim();
    return {
      id: tc.id || tc.name,
      tool: tc.name,
      title: TITLES[tc.name] ?? tc.name.replace(/_/g, ' '),
      rows: [],
      code: [],
      moreLines: 0,
      note: tc.success ? error : error || 'This call failed, so the answer does not use it.',
      seconds,
      ok: tc.success,
    };
  }
  const view = describe(tc.name, args, data);
  const lines = (view.code ?? '').trim() ? (view.code ?? '').trim().split('\n') : [];
  return {
    id: tc.id || tc.name,
    tool: tc.name,
    title: view.title,
    rows: view.rows,
    code: lines.slice(0, CODE_LINES),
    moreLines: Math.max(0, lines.length - CODE_LINES),
    note: view.note,
    seconds,
    ok: true,
  };
}

/** Every tool call Copilot made in the thread, numbered in the order they ran. */
export function threadSources(messages: readonly AgentMessage[]): SourceView[] {
  const out: SourceView[] = [];
  for (const m of messages) {
    if (m.role === MessageRole.USER) continue;
    for (const tc of m.toolCalls ?? []) {
      out.push({ ...describeSource(tc), n: out.length + 1, messageId: m.id });
    }
  }
  return out;
}

/** "3 tool calls · 1.8 s", or just the count when no call reported its time. */
export function sourcesSummary(sources: readonly SourceView[]): string {
  const total = sources.reduce((sum, s) => sum + (s.seconds ?? 0), 0);
  const calls = count(sources.length, 'tool call');
  return total > 0 ? `${calls} · ${total.toFixed(1)} s` : calls;
}
