import { useAgentStore } from '@llamatrade/core/stores/agent';
import { ArrowLeft, History, Play, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useStrategyBuilderStoreWithContext, type ViewMode } from '../../store/strategy-builder';
import { Segmented } from '../ui';

interface EditorHeaderProps {
  onSave: () => void;
  onBacktest: () => void;
  sessionVersion: number | null;
  hasSession: boolean;
  canSave: boolean;
}

const MODES = [
  { key: 'tree', label: 'Outline' },
  { key: 'code', label: 'Code' },
] as const;

export function EditorHeader({
  onSave,
  onBacktest,
  sessionVersion,
  hasSession,
  canSave,
}: EditorHeaderProps) {
  const {
    strategyId,
    strategyName,
    setStrategyName,
    serverVersion,
    isDirty,
    viewMode,
    setViewMode,
  } = useStrategyBuilderStoreWithContext();
  const togglePanel = useAgentStore((s) => s.togglePanel);
  const nextVersion = strategyId ? serverVersion + 1 : 1;

  const meta = !strategyId
    ? 'New strategy · not saved yet'
    : isDirty
      ? `Version ${nextVersion} draft · unsaved changes`
      : `Version ${serverVersion} · saved`;
  const sessionNote = hasSession
    ? ` · version ${sessionVersion ?? serverVersion} runs in paper`
    : '';

  const backtestBlocked = !strategyId || isDirty;
  const mode: 'tree' | 'code' = viewMode === 'code' ? 'code' : 'tree';

  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <Link
          to={strategyId ? `/strategies/${strategyId}` : '/strategies'}
          className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {strategyId ? 'Strategy' : 'Strategies'}
        </Link>
        <label className="sr-only" htmlFor="strategy-name">
          Strategy name
        </label>
        <input
          id="strategy-name"
          value={strategyName}
          onChange={(e) => setStrategyName(e.target.value)}
          className="mt-1 block w-full min-w-0 rounded-[4px] bg-transparent text-[22px] font-semibold tracking-[-0.015em] text-fg outline-none hover:bg-sunk/60 focus:bg-sunk"
        />
        <p className="m-0 mt-0.5 text-[12.5px] text-fg-3">
          {meta}
          {sessionNote}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="Editor view"
          options={MODES}
          value={mode}
          onChange={(k) => setViewMode(k as ViewMode)}
        />
        {strategyId && (
          <Link to={`/strategies/${strategyId}/versions`} className="btn btn-ghost">
            <History className="h-4 w-4" />
            <span className="sr-only sm:not-sr-only">Versions</span>
          </Link>
        )}
        <button type="button" onClick={togglePanel} className="btn btn-ghost">
          <Sparkles className="h-4 w-4" />
          <span className="sr-only sm:not-sr-only">Copilot</span>
        </button>
        <button type="button" onClick={onSave} disabled={!canSave} className="btn btn-secondary">
          Save version {nextVersion}
        </button>
        <button
          type="button"
          onClick={onBacktest}
          disabled={backtestBlocked}
          title={backtestBlocked ? 'Save this version to backtest it.' : undefined}
          className="btn btn-primary"
        >
          <Play className="h-4 w-4" />
          Backtest
        </button>
      </div>
    </header>
  );
}
