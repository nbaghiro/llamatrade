import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import {
  ArrowRight,
  CornerDownLeft,
  FileText,
  FlaskConical,
  LineChart,
  Plus,
  Search,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';

import {
  COPILOT_RESULT_ID,
  copilotUrl,
  flattenGroups,
  highlightRuns,
  moveActive,
  rankPalette,
  type PaletteItem,
  type PaletteKind,
} from '../../lib/palette';
import { useUIStore } from '../../store/ui';
import { Kbd } from '../ui/Kbd';
import { useModal } from '../ui/useModal';

import { usePalette } from './usePalette';

const PAGES: ReadonlyArray<PaletteItem & { to: string }> = [
  { id: 'page:home', kind: 'page', label: 'Home', to: '/dashboard', keywords: ['dashboard'] },
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
  { id: 'page:copilot', kind: 'page', label: 'Copilot', to: '/copilot' },
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
    label: 'Deploy a strategy',
    hint: 'Runs in paper',
    keywords: ['run', 'start', 'session'],
  },
];

const EMPTY_IDS = [
  'action:new',
  'action:backtest',
  'page:portfolio',
  'page:strategies',
  'page:copilot',
];

const STATUS_HINT: Partial<Record<StrategyStatus, string>> = {
  [StrategyStatus.DRAFT]: 'Draft',
  [StrategyStatus.ACTIVE]: 'Active',
  [StrategyStatus.PAUSED]: 'Paused',
  [StrategyStatus.ARCHIVED]: 'Archived',
};

const KIND_ICON: Record<PaletteKind, LucideIcon> = {
  strategy: LineChart,
  page: FileText,
  action: Plus,
  copilot: Sparkles,
};

const ACTION_ICON: Record<ActionId, LucideIcon> = {
  'action:new': Plus,
  'action:backtest': FlaskConical,
  'action:funds': Plus,
  'action:deploy': ArrowRight,
};

export function CommandPalette() {
  const open = usePalette((s) => s.open);
  return open ? <PaletteDialog /> : null;
}

function PaletteDialog() {
  const navigate = useNavigate();
  const hide = usePalette((s) => s.hide);
  const openNewStrategyDialog = useUIStore((s) => s.openNewStrategyDialog);
  const strategies = useStrategiesStore((s) => s.strategies);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const panel = useModal(true, hide);
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  useEffect(() => {
    input.current?.focus();
    if (strategies.length === 0) fetchStrategies().catch(() => undefined);
  }, [strategies.length, fetchStrategies]);

  const items = useMemo<PaletteItem[]>(
    () => [
      ...strategies.map((s) => ({
        id: `strategy:${s.id}`,
        kind: 'strategy' as const,
        label: s.name,
        hint: STATUS_HINT[s.status],
        keywords: s.symbols,
      })),
      ...PAGES,
      ...ACTIONS,
    ],
    [strategies]
  );

  const groups = useMemo(() => rankPalette(query, items, { emptyIds: EMPTY_IDS }), [query, items]);
  const flat = useMemo(() => flattenGroups(groups), [groups]);
  const current = flat[Math.min(active, flat.length - 1)];

  useEffect(() => {
    setActive(0);
  }, [query]);

  const run = (id: string) => {
    hide();
    if (id === COPILOT_RESULT_ID) return navigate(copilotUrl(query));
    if (id.startsWith('strategy:')) return navigate(`/strategies/${id.slice('strategy:'.length)}`);
    const page = PAGES.find((p) => p.id === id);
    if (page) return navigate(page.to);
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
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if ((e.metaKey || e.ctrlKey) && query.trim()) run(COPILOT_RESULT_ID);
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
        className="flex h-full w-full flex-col overflow-hidden bg-canvas outline-none sm:h-auto sm:max-w-[640px] sm:rounded-[12px] sm:border sm:border-line-strong sm:bg-panel sm:shadow-xl"
      >
        <div className="flex h-[52px] items-center gap-2.5 border-b border-line px-[18px]">
          <Search className="h-[18px] w-[18px] flex-none text-fg-3" />
          <input
            ref={input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search strategies, pages and actions"
            aria-label="Search"
            aria-controls="palette-results"
            aria-activedescendant={current ? `palette-${current.id}` : undefined}
            className="min-w-0 flex-1 bg-transparent text-base text-fg outline-none placeholder:text-fg-3"
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
          className="min-h-0 flex-1 overflow-y-auto py-1 sm:max-h-[min(60vh,440px)] sm:flex-none"
        >
          {groups.map((g) => (
            <div key={g.kind} role="group" aria-label={g.title}>
              <div className="px-[18px] pb-1 pt-2.5 font-mono text-[11px] font-medium text-fg-3">
                {g.title}
              </div>
              {g.results.map((r) => {
                row += 1;
                const index = row;
                const on = current?.id === r.id;
                const Icon =
                  r.kind === 'action' ? ACTION_ICON[r.id as ActionId] : KIND_ICON[r.kind];
                return (
                  <div
                    key={r.id}
                    id={`palette-${r.id}`}
                    role="option"
                    aria-selected={on}
                    onMouseMove={() => setActive(index)}
                    onClick={() => run(r.id)}
                    className={`flex cursor-pointer items-center gap-3 px-[18px] py-2 ${on ? 'bg-sunk text-fg' : 'text-fg-2'}`}
                  >
                    <Icon className={`h-4 w-4 flex-none ${on ? 'text-accent' : 'text-fg-3'}`} />
                    <b className="min-w-0 truncate font-medium text-fg">
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
                    <span className="ml-auto flex flex-none items-center gap-2 text-xs text-fg-3">
                      {r.hint}
                      {on && <CornerDownLeft className="h-3.5 w-3.5" />}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div className="hidden gap-4 border-t border-line bg-sunk px-[18px] py-2.5 text-xs text-fg-3 sm:flex">
          <span>
            <Kbd>↑↓</Kbd> move
          </span>
          <span>
            <Kbd>↵</Kbd> open
          </span>
          <span>
            <Kbd>⌘↵</Kbd> ask Copilot
          </span>
        </div>
      </div>
    </div>,
    document.body
  );
}
