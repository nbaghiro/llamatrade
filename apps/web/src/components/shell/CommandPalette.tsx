import { num, toDate } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import {
  AlertTriangle,
  CalendarClock,
  ArrowRight,
  Clock3,
  CornerDownLeft,
  FileText,
  FlaskConical,
  History,
  LineChart,
  Plus,
  Receipt,
  Search,
} from 'lucide-react';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';

import { formatMoney, formatPct, moveTone, TONE_TEXT } from '../../lib/format';
import { etParts } from '../../lib/marketClock';
import {
  COPILOT_RESULT_ID,
  copilotUrl,
  flattenGroups,
  highlightRuns,
  moveActive,
  parseQuery,
  pushRecent,
  rankPalette,
  type PaletteItem,
  type PaletteKind,
  type RecentEntry,
} from '../../lib/palette';
import { useUIStore } from '../../store/ui';
import { CopilotMark } from '../common/Logo';
import { etDay, homeSessions, marketPhase, rebalancingToday } from '../home/homeModel';
import { useAttentionEntries } from '../home/useAttentionEntries';
import { Kbd } from '../ui/Kbd';
import { ModeBadge } from '../ui/ModeBadge';
import { useModal } from '../ui/useModal';

import { usePalette } from './usePalette';
import { useSessionRows } from './useSessionRows';

const PAGES: ReadonlyArray<PaletteItem & { to: string }> = [
  {
    id: 'page:home',
    kind: 'page',
    label: 'Home',
    to: '/dashboard',
    keywords: ['dashboard', 'copilot', 'chat'],
  },
  {
    id: 'page:markets',
    kind: 'page',
    label: 'Markets',
    to: '/markets',
    keywords: ['prices', 'quotes', 'watchlist'],
  },
  {
    id: 'page:portfolio',
    kind: 'page',
    label: 'Portfolio',
    to: '/portfolio',
    keywords: ['positions', 'holdings'],
  },
  { id: 'page:strategies', kind: 'page', label: 'Strategies', to: '/strategies' },
  {
    id: 'page:templates',
    kind: 'page',
    label: 'Strategies › Templates',
    to: '/strategies/templates',
  },
  { id: 'page:backtests', kind: 'page', label: 'Backtests', to: '/backtests' },
  { id: 'page:new-backtest', kind: 'page', label: 'New backtest', to: '/backtest' },
  {
    id: 'page:sessions',
    kind: 'page',
    label: 'Sessions',
    to: '/trading',
    keywords: ['orders', 'trading'],
  },
  {
    id: 'page:copilot',
    kind: 'page',
    label: 'Conversations',
    to: '/dashboard?view=history',
    keywords: ['copilot', 'chat', 'history'],
  },
  {
    id: 'page:settings',
    kind: 'page',
    label: 'Settings',
    to: '/settings',
    keywords: ['account', 'profile'],
  },
  {
    id: 'page:notifications',
    kind: 'page',
    label: 'Settings › Notifications',
    to: '/settings/notifications',
    keywords: ['email', 'webhook', 'alerts'],
  },
  {
    id: 'page:appearance',
    kind: 'page',
    label: 'Settings › Appearance',
    to: '/settings/appearance',
    keywords: ['theme', 'dark', 'light', 'accent'],
  },
  {
    id: 'page:plan',
    kind: 'page',
    label: 'Plan and usage',
    to: '/settings/plan',
    keywords: ['billing', 'invoices', 'subscription'],
  },
];

type ActionId = 'action:new' | 'action:backtest' | 'action:funds' | 'action:deploy';

const ACTIONS: ReadonlyArray<PaletteItem & { id: ActionId }> = [
  { id: 'action:new', kind: 'action', label: 'New strategy', keywords: ['create', 'draft'] },
  { id: 'action:backtest', kind: 'action', label: 'Run backtest', keywords: ['test', 'simulate'] },
  {
    id: 'action:funds',
    kind: 'action',
    label: 'Add paper funds',
    keywords: ['deposit', 'wallet', 'cash'],
  },
  {
    id: 'action:deploy',
    kind: 'action',
    label: 'Start a strategy',
    hint: 'Runs in paper',
    keywords: ['run', 'start', 'session'],
  },
];

const FALLBACK_EMPTY_IDS = ['action:new', 'action:backtest', 'page:markets', 'page:copilot'];
const RECENT_KEY = 'llamatrade-palette-recent';
const PALETTE_SESSIONS = 6;

const STATUS_HINT: Partial<Record<StrategyStatus, string>> = {
  [StrategyStatus.DRAFT]: 'Draft',
  [StrategyStatus.ACTIVE]: 'Active',
  [StrategyStatus.PAUSED]: 'Paused',
  [StrategyStatus.ARCHIVED]: 'Archived',
};

type PaletteIcon = ComponentType<{ className?: string }>;

const KIND_ICON: Record<PaletteKind, PaletteIcon> = {
  today: Clock3,
  session: LineChart,
  recent: History,
  strategy: LineChart,
  page: FileText,
  action: Plus,
  copilot: CopilotMark,
};

const ACTION_ICON: Record<ActionId, PaletteIcon> = {
  'action:new': Plus,
  'action:backtest': FlaskConical,
  'action:funds': Plus,
  'action:deploy': ArrowRight,
};

function readRecent(): RecentEntry[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter(
          (e): e is RecentEntry =>
            typeof e === 'object' &&
            e !== null &&
            typeof (e as RecentEntry).id === 'string' &&
            typeof (e as RecentEntry).label === 'string' &&
            typeof (e as RecentEntry).to === 'string'
        )
      : [];
  } catch {
    return [];
  }
}

function writeRecent(list: readonly RecentEntry[]) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {
    // Recent is a convenience; without storage the palette still works.
  }
}

/** What a row shows beyond its label, and where it goes. */
interface RowExtra {
  to?: string;
  icon?: PaletteIcon;
  mode?: 'live' | 'paper';
  dot?: 'accent' | 'muted' | 'risk';
  right?: ReactNode;
}

const sameEtDay = (a: Date, b: Date) => {
  const x = etParts(a);
  const y = etParts(b);
  return x.year === y.year && x.month === y.month && x.day === y.day;
};

const shortDate = (d: Date) =>
  d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' });

export function CommandPalette() {
  const open = usePalette((s) => s.open);
  return open ? <PaletteDialog /> : null;
}

/** Useful before you type: today, your sessions and what you opened recently (palette2 A). */
function PaletteDialog() {
  const navigate = useNavigate();
  const hide = usePalette((s) => s.hide);
  const openNewStrategyDialog = useUIStore((s) => s.openNewStrategyDialog);
  const strategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const sessionRows = useSessionRows();
  const orders = useTradingStore((s) => s.orders);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const attention = useAttentionEntries();
  const panel = useModal(true, hide);
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [recent] = useState(readRecent);

  useEffect(() => {
    input.current?.focus();
    if (strategies.length === 0) fetchStrategies().catch(() => undefined);
    loadBlotter().catch(() => undefined);
    // Loads once when the palette opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { items, extras, emptyIds } = useMemo(() => {
    const now = new Date();
    const extras = new Map<string, RowExtra>();
    const today: PaletteItem[] = attention.map((a) => {
      const id = `today:${a.id}`;
      extras.set(id, { to: a.href, icon: AlertTriangle, dot: 'risk' });
      return { id, kind: 'today' as const, label: a.title.replace(/\.$/, '') };
    });
    const fills = orders.filter((o) => {
      const at = toDate(o.filledAt);
      return o.status === OrderStatus.FILLED && at !== null && sameEtDay(at, now);
    });
    if (fills.length) {
      const traded = fills.reduce(
        (sum, o) => sum + num(o.filledQuantity) * num(o.averageFillPrice),
        0
      );
      extras.set('today:fills', {
        to: '/trading',
        icon: Receipt,
        right: `${formatMoney(traded)} traded`,
      });
      today.push({
        id: 'today:fills',
        kind: 'today',
        label: `${fills.length} fill${fills.length === 1 ? '' : 's'} today`,
        keywords: ['orders', 'trades'],
      });
    }

    const phase = marketPhase(now);
    if (phase.open) {
      for (const s of rebalancingToday(homeSessions(sessionRows, []), etDay(now))) {
        const id = `today:rebalance:${s.id}`;
        extras.set(id, {
          to: s.href,
          icon: CalendarClock,
          mode: s.mode,
          dot: s.state === 'frozen' ? 'risk' : 'accent',
          right: s.state === 'frozen' ? 'Waits for review' : `Before the ${phase.closeClock} close`,
        });
        today.push({
          id,
          kind: 'today',
          label: `${s.name} rebalances today`,
          keywords: ['rebalance'],
        });
      }
    }

    const sessionItems: PaletteItem[] = [...sessionRows]
      .sort((a, b) => Number(b.view.open) - Number(a.view.open))
      .slice(0, PALETTE_SESSIONS)
      .map((r) => {
        const id = `session:${r.session.id}`;
        const move = r.figures.todayPct;
        const ended = toDate(r.session.endedAt);
        const right = r.view.open ? (
          <>
            {move !== null && (
              <span className={`num ${TONE_TEXT[moveTone(move * 100)]}`}>
                {formatPct(move, { signed: true })}
              </span>
            )}
            {r.figures.equity !== null && (
              <span className="num text-fg-2">{formatMoney(r.figures.equity)}</span>
            )}
          </>
        ) : (
          <span>{ended ? `Stopped ${shortDate(ended)}` : r.view.label}</span>
        );
        extras.set(id, {
          to: `/trading/${r.session.id}`,
          mode: r.session.mode === ExecutionMode.LIVE ? 'live' : 'paper',
          dot: r.state === 'frozen' ? 'risk' : r.view.open ? 'accent' : 'muted',
          right,
        });
        return { id, kind: 'session' as const, label: r.name, keywords: ['session'] };
      });

    const recentItems: PaletteItem[] = recent.map((r) => {
      const id = `recent:${r.id}`;
      extras.set(id, { to: r.to, right: shortDate(new Date(r.at)) });
      return { id, kind: 'recent' as const, label: r.label };
    });

    const strategyItems: PaletteItem[] = strategies.map((s) => {
      const id = `strategy:${s.id}`;
      extras.set(id, { to: `/strategies/${s.id}` });
      return {
        id,
        kind: 'strategy' as const,
        label: s.name,
        hint: STATUS_HINT[s.status],
        keywords: s.symbols,
      };
    });
    for (const p of PAGES) extras.set(p.id, { to: p.to });

    const emptyIds = [...today, ...sessionItems, ...recentItems].map((i) => i.id);
    return {
      items: [...today, ...sessionItems, ...recentItems, ...strategyItems, ...PAGES, ...ACTIONS],
      extras,
      emptyIds: emptyIds.length ? emptyIds : FALLBACK_EMPTY_IDS,
    };
  }, [attention, orders, sessionRows, recent, strategies]);

  const { actionsOnly, query: text } = parseQuery(query);
  const groups = useMemo(() => {
    const pool = actionsOnly
      ? items.filter((i) => i.kind === 'action')
      : text.trim()
        ? items.filter((i) => i.kind !== 'recent')
        : items;
    return rankPalette(text, pool, { emptyIds: actionsOnly ? ACTIONS.map((a) => a.id) : emptyIds });
  }, [actionsOnly, text, items, emptyIds]);
  const flat = useMemo(() => flattenGroups(groups), [groups]);
  const current = flat[Math.min(active, flat.length - 1)];

  useEffect(() => {
    setActive(0);
  }, [query]);

  const remember = (id: string, label: string, to: string) => {
    if (id.startsWith('recent:') || id.startsWith('today:')) return;
    writeRecent(pushRecent(readRecent(), { id, label, to, at: Date.now() }));
  };

  const run = (id: string) => {
    hide();
    if (id === COPILOT_RESULT_ID) return navigate(copilotUrl(text));
    const row = flat.find((r) => r.id === id);
    const to = extras.get(id)?.to;
    if (to) {
      if (row) remember(id, row.label, to);
      return navigate(to);
    }
    switch (id as ActionId) {
      case 'action:new':
        return openNewStrategyDialog();
      case 'action:backtest':
        return navigate('/backtest');
      case 'action:funds':
        return navigate('/portfolio?funds=add');
      case 'action:deploy':
        return navigate('/strategies');
    }
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => moveActive(i, e.key === 'ArrowDown' ? 1 : -1, flat.length));
    } else if (e.key === 'Tab' && !e.shiftKey && text.trim()) {
      e.preventDefault();
      run(COPILOT_RESULT_ID);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if ((e.metaKey || e.ctrlKey) && text.trim()) run(COPILOT_RESULT_ID);
      else if (current) run(current.id);
    }
  };

  let row = -1;
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center sm:px-3 sm:pt-[12vh]"
      style={{ background: 'var(--scrim)' }}
      onMouseDown={(e) => e.target === e.currentTarget && hide()}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="Search or jump to"
        tabIndex={-1}
        className="flex h-full w-full flex-col overflow-hidden bg-canvas outline-none sm:h-auto sm:max-w-[680px] sm:rounded-[14px] sm:border sm:border-line-strong sm:bg-panel sm:shadow-xl"
      >
        <div className="flex h-[58px] items-center gap-3 border-b border-line px-5">
          <Search className="h-[18px] w-[18px] flex-none text-fg-3" />
          <input
            ref={input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search, or type an action"
            aria-label="Search"
            aria-controls="palette-results"
            aria-activedescendant={current ? `palette-${current.id}` : undefined}
            className="min-w-0 flex-1 bg-transparent text-[16px] text-fg outline-none placeholder:text-fg-3"
          />
          <Kbd className="hidden sm:inline">esc</Kbd>
          <button
            type="button"
            onClick={hide}
            className="flex-none text-[14px] font-medium text-accent sm:hidden"
          >
            Cancel
          </button>
        </div>

        <div
          id="palette-results"
          role="listbox"
          className="min-h-0 flex-1 overflow-y-auto px-2 py-1.5 sm:max-h-[min(62vh,480px)] sm:flex-none"
        >
          {groups.map((g) => (
            <div key={g.kind} role="group" aria-label={g.title}>
              <div className="kicker px-3 pb-1.5 pt-3 uppercase tracking-[0.06em]">{g.title}</div>
              {g.results.map((r) => {
                row += 1;
                const index = row;
                const on = current?.id === r.id;
                const extra = extras.get(r.id);
                const Icon =
                  extra?.icon ??
                  (r.kind === 'action' ? ACTION_ICON[r.id as ActionId] : KIND_ICON[r.kind]);
                return (
                  <div
                    key={r.id}
                    id={`palette-${r.id}`}
                    role="option"
                    aria-selected={on}
                    onMouseMove={() => setActive(index)}
                    onClick={() => run(r.id)}
                    className={`flex cursor-pointer items-center gap-3 rounded-[9px] px-3 py-2.5 ${on ? 'bg-sunk text-fg' : 'text-fg-2'}`}
                  >
                    {extra?.dot ? (
                      <i
                        aria-hidden="true"
                        className={`mx-[5px] h-1.5 w-1.5 flex-none ${extra.dot === 'muted' ? 'bg-fg-3' : extra.dot === 'risk' ? 'rounded-full bg-risk' : 'rounded-full bg-accent'}`}
                      />
                    ) : (
                      <Icon className={`h-4 w-4 flex-none ${on ? 'text-fg' : 'text-fg-3'}`} />
                    )}
                    <b className="min-w-0 truncate text-[14px] font-medium text-fg">
                      {highlightRuns(r.label, r.matches).map((run, i) =>
                        run.hit ? (
                          <mark key={i} className="rounded-sm bg-accent-soft text-fg">
                            {run.text}
                          </mark>
                        ) : (
                          <span key={i}>{run.text}</span>
                        )
                      )}
                    </b>
                    {extra?.mode && <ModeBadge mode={extra.mode} size="sm" />}
                    <span className="ml-auto flex flex-none items-center gap-2.5 text-[12.5px] text-fg-3">
                      {extra?.right ?? r.hint}
                      {on && <CornerDownLeft className="h-3.5 w-3.5" />}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div className="hidden items-center gap-4 border-t border-line bg-sunk px-5 py-2.5 text-xs text-fg-3 sm:flex">
          <span>
            <Kbd>↑</Kbd> <Kbd>↓</Kbd> move
          </span>
          <span>
            <Kbd>↵</Kbd> open
          </span>
          <span>
            <Kbd>tab</Kbd> ask Copilot
          </span>
          <span className="ml-auto">Type &gt; for actions</span>
        </div>
      </div>
    </div>,
    document.body
  );
}
