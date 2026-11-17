import { ChevronDown, History } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useStrategyBuilderStoreWithContext, type ViewMode } from '../../store/strategy-builder';
import { Menu, PageHead, Segmented } from '../ui';

const MODES = [
  { key: 'tree', label: 'Blocks' },
  { key: 'code', label: 'Code' },
  { key: 'split', label: 'Split' },
] as const;

export interface HeaderBacktest {
  label: string;
  disabled: boolean;
  title?: string;
  onRun: () => void;
  /** The Backtests page with every setting, for runs that need other dates or capital. */
  settingsHref: string | null;
}

interface EditorHeaderProps {
  /** "v4 draft", "Draft", "v4". */
  chip: string;
  chipTone: 'draft' | 'saved';
  meta: ReactNode;
  save: ReactNode;
  backtest: HeaderBacktest | null;
  /** True on a phone: only Blocks, and no split. */
  compact: boolean;
}

/** The editor's page head: name, version and state, the view, then backtest and save. */
export function EditorHeader({ chip, chipTone, meta, save, backtest, compact }: EditorHeaderProps) {
  const { strategyId, strategyName, setStrategyName, viewMode, setViewMode } =
    useStrategyBuilderStoreWithContext();
  const modes = compact ? [] : MODES;

  return (
    <PageHead
      documentTitle={strategyName || 'Untitled strategy'}
      crumbs={[
        { label: 'Strategies', to: '/strategies' },
        ...(strategyId ? [{ label: strategyName, to: `/strategies/${strategyId}` }] : []),
      ]}
      title={
        <>
          <label className="sr-only" htmlFor="strategy-name">
            Strategy name
          </label>
          <input
            id="strategy-name"
            value={strategyName}
            placeholder="Untitled strategy"
            onChange={(e) => setStrategyName(e.target.value)}
            className="-ml-1 block w-full min-w-0 rounded-[4px] bg-transparent px-1 font-[inherit] text-inherit outline-none hover:bg-sunk/60 focus:bg-sunk md:w-[min(560px,48vw)]"
          />
        </>
      }
      sub={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            className={`rounded-[4px] px-1.5 py-px font-mono text-[11.5px] ${
              chipTone === 'draft'
                ? 'border border-dashed border-line-strong text-fg-2'
                : 'border border-accent/40 bg-accent-soft text-accent'
            }`}
          >
            {chip}
          </span>
          <span className="text-[12.5px] text-fg-3">{meta}</span>
        </span>
      }
      actions={
        <>
          {modes.length > 0 && (
            <Segmented
              label="Editor view"
              options={modes}
              value={viewMode}
              onChange={(k) => setViewMode(k as ViewMode)}
            />
          )}
          {strategyId && !compact && (
            <Link to={`/strategies/${strategyId}/versions`} className="btn btn-ghost">
              <History className="h-4 w-4" />
              Versions
            </Link>
          )}
          {backtest && (
            <span className="flex">
              <button
                type="button"
                onClick={backtest.onRun}
                disabled={backtest.disabled}
                title={backtest.title}
                className={`btn btn-secondary ${backtest.settingsHref ? 'rounded-r-none' : ''}`}
              >
                {backtest.label}
              </button>
              {backtest.settingsHref && (
                <Menu
                  label="Other backtest settings"
                  width={260}
                  trigger={(p) => (
                    <button
                      type="button"
                      {...p}
                      aria-label="Other backtest settings"
                      className="btn btn-secondary rounded-l-none border-l-0 px-2"
                    >
                      <ChevronDown className="h-4 w-4" />
                    </button>
                  )}
                  items={[
                    {
                      kind: 'link',
                      label: 'Choose dates and capital on the Backtests page',
                      to: backtest.settingsHref,
                    },
                  ]}
                />
              )}
            </span>
          )}
          {save}
        </>
      }
    />
  );
}
