import {
  ArrowLeft,
  ChevronDown,
  Code2,
  Columns2,
  GitBranch,
  Loader2,
  Play,
  Redo2,
  Share2,
  Trash2,
  Undo2,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useRunConsole } from '../../../store/runConsole';
import { useStrategyBuilderStoreWithContext, type ViewMode } from '../../../store/strategy-builder';
import { Select } from '../../common/Select';

const TIMEFRAME_OPTIONS = [
  { value: '1m', label: '1 Minute' },
  { value: '5m', label: '5 Minutes' },
  { value: '15m', label: '15 Minutes' },
  { value: '1H', label: '1 Hour' },
  { value: '4H', label: '4 Hours' },
  { value: '1D', label: 'Daily' },
  { value: '1W', label: 'Weekly' },
  { value: '1M', label: 'Monthly' },
];

const TIMEFRAME_LABEL: Record<string, string> = Object.fromEntries(
  TIMEFRAME_OPTIONS.map((o) => [o.value, o.label])
);

interface ModeButtonProps {
  mode: ViewMode;
  current: ViewMode;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}

function ModeButton({ mode, current, icon, label, onClick }: ModeButtonProps) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`p-1.5 transition-colors ${
        mode === current ? 'bg-ink text-bone' : 'text-ink/50 hover:bg-ink/10 hover:text-ink'
      }`}
    >
      {icon}
    </button>
  );
}

interface BuilderTopBarProps {
  readOnly?: boolean;
}

/**
 * The Split Studio top bar — the builder's primary chrome. Holds identity,
 * history, the Tree/Split/Code switch, save, and backtest. Replaces the old
 * LeftPanel + RootBlock header so the tree/code panes get the full width.
 */
export function BuilderTopBar({ readOnly }: BuilderTopBarProps) {
  const navigate = useNavigate();
  const {
    tree,
    ui,
    viewMode,
    setViewMode,
    strategyId,
    strategyName,
    strategyDescription,
    timeframe,
    isDirty,
    saving,
    setStrategyName,
    setStrategyDescription,
    setTimeframe,
    saveStrategy,
    undo,
    redo,
    canUndo,
    canRedo,
    deleteBlock,
    getBlock,
  } = useStrategyBuilderStoreWithContext();
  const openRunConsole = useRunConsole((s) => s.openRunConsole);

  const [detailsOpen, setDetailsOpen] = useState(false);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);
  const [savingAndExiting, setSavingAndExiting] = useState(false);
  const detailsRef = useRef<HTMLDivElement>(null);

  const positions = Object.values(tree.blocks).filter((b) => b.type === 'asset').length;
  const selected = ui.selectedBlockId ? getBlock(ui.selectedBlockId) : null;
  const canDelete = !!selected && selected.type !== 'root';

  useEffect(() => {
    if (!detailsOpen) return;
    const onDown = (e: MouseEvent) => {
      if (detailsRef.current && !detailsRef.current.contains(e.target as Node)) setDetailsOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [detailsOpen]);

  const handleBack = () => {
    if (isDirty) setShowLeaveConfirm(true);
    else navigate('/strategies');
  };

  const handleSave = async () => {
    const wasNew = !strategyId;
    const savedId = await saveStrategy();
    if (savedId && wasNew) navigate(`/strategies/${savedId}`, { replace: true });
  };

  const handleSaveAndExit = async () => {
    setSavingAndExiting(true);
    const savedId = await saveStrategy();
    setSavingAndExiting(false);
    if (savedId) {
      setShowLeaveConfirm(false);
      navigate('/strategies');
    }
  };

  // Read-only previews get a slim identity + view switch only.
  if (readOnly) {
    return (
      <div className="flex h-11 flex-shrink-0 items-center gap-3 border-b-2 border-ink bg-paper px-4">
        <div className="flex items-center gap-2 p-1.5 bg-orange-500 border-2 border-ink">
          <GitBranch className="h-3.5 w-3.5 text-ink" />
        </div>
        <span className="font-display text-lg uppercase leading-none tracking-tight">{strategyName}</span>
        <div className="ml-auto flex items-center border-2 border-ink bg-paper p-0.5">
          <ModeButton mode="tree" current={viewMode} icon={<GitBranch size={14} />} label="Tree" onClick={() => setViewMode('tree')} />
          <ModeButton mode="code" current={viewMode} icon={<Code2 size={14} />} label="Code" onClick={() => setViewMode('code')} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b-2 border-ink bg-paper px-3 py-2">
      {/* Identity */}
      <button
        onClick={handleBack}
        title="Back to Strategies"
        className="flex h-8 w-8 items-center justify-center border-2 border-ink bg-paper text-ink transition-colors hover:bg-ink hover:text-bone"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>

      <input
        value={strategyName}
        onChange={(e) => setStrategyName(e.target.value)}
        aria-label="Strategy name"
        className="min-w-[8ch] max-w-[26ch] border-2 border-transparent bg-transparent px-1 py-0.5 font-display text-xl uppercase leading-none tracking-tight text-ink outline-none hover:border-ink/20 focus:border-orange-500"
        style={{ width: `${Math.max(8, Math.min(26, strategyName.length + 1))}ch` }}
      />

      <div className="flex items-center gap-1.5">
        <span className="border-2 border-ink px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide">DSL</span>
        <span className="border-2 border-ink px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide">
          {TIMEFRAME_LABEL[timeframe] ?? timeframe}
        </span>
        <span className="border-2 border-ink px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide tabular-nums">
          {positions} pos
        </span>
      </div>

      {/* Details popover */}
      <div className="relative" ref={detailsRef}>
        <button
          onClick={() => setDetailsOpen((v) => !v)}
          className="flex items-center gap-1 border-2 border-ink bg-paper px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wide text-ink/70 hover:bg-ink/5"
        >
          Details <ChevronDown className={`h-3 w-3 transition-transform ${detailsOpen ? 'rotate-180' : ''}`} />
        </button>
        {detailsOpen && (
          <div className="absolute left-0 top-full z-50 mt-2 w-72 border-2 border-ink bg-paper p-3 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
            <label className="mb-1 block font-mono text-[10px] font-bold uppercase tracking-wide text-ink/70">
              Description
            </label>
            <textarea
              value={strategyDescription}
              onChange={(e) => setStrategyDescription(e.target.value)}
              rows={3}
              placeholder="Describe your strategy…"
              className="mb-3 w-full resize-none border-2 border-ink bg-paper px-2 py-1.5 text-sm text-ink outline-none placeholder:text-ink/40 focus:border-orange-500"
            />
            <label className="mb-1 block font-mono text-[10px] font-bold uppercase tracking-wide text-ink/70">
              Timeframe
            </label>
            <Select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} options={TIMEFRAME_OPTIONS} />
          </div>
        )}
      </div>

      {isDirty && <span className="h-2.5 w-2.5 border-2 border-ink bg-orange-500" title="Unsaved changes" />}

      {/* Right cluster */}
      <div className="ml-auto flex items-center gap-2">
        <div className="flex items-center border-2 border-ink">
          <button
            onClick={() => canUndo() && undo()}
            disabled={!canUndo()}
            title="Undo"
            className="p-1.5 text-ink transition-colors hover:bg-ink hover:text-bone disabled:cursor-not-allowed disabled:text-ink/25 disabled:hover:bg-transparent"
          >
            <Undo2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => canRedo() && redo()}
            disabled={!canRedo()}
            title="Redo"
            className="border-l-2 border-ink p-1.5 text-ink transition-colors hover:bg-ink hover:text-bone disabled:cursor-not-allowed disabled:text-ink/25 disabled:hover:bg-transparent"
          >
            <Redo2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => ui.selectedBlockId && deleteBlock(ui.selectedBlockId)}
            disabled={!canDelete}
            title="Delete selected"
            className="border-l-2 border-ink p-1.5 text-red-600 transition-colors hover:bg-red-500 hover:text-bone disabled:cursor-not-allowed disabled:text-ink/25 disabled:hover:bg-transparent"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex items-center border-2 border-ink bg-paper p-0.5">
          <ModeButton mode="tree" current={viewMode} icon={<GitBranch size={14} />} label="Tree" onClick={() => setViewMode('tree')} />
          <ModeButton mode="split" current={viewMode} icon={<Columns2 size={14} />} label="Split" onClick={() => setViewMode('split')} />
          <ModeButton mode="code" current={viewMode} icon={<Code2 size={14} />} label="Code" onClick={() => setViewMode('code')} />
        </div>

        <button
          className="hidden items-center gap-1.5 border-2 border-transparent px-2 py-1.5 font-mono text-[11px] font-bold uppercase tracking-wide text-ink/50 hover:text-ink sm:flex"
          title="Share"
        >
          <Share2 className="h-3.5 w-3.5" /> Share
        </button>

        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="flex items-center gap-2 border-2 border-ink bg-orange-500 px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-wide text-ink shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-all hover:bg-ink hover:text-orange-500 disabled:opacity-40 disabled:hover:bg-orange-500 disabled:hover:text-ink"
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          {saving ? 'Saving' : 'Save'}
        </button>

        {strategyId ? (
          <button
            onClick={() => openRunConsole(strategyId, strategyName)}
            className="flex items-center gap-1.5 border-2 border-ink bg-paper px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-wide text-ink shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-all hover:bg-ink hover:text-bone"
          >
            <Play className="h-3 w-3 fill-current" /> Backtest
          </button>
        ) : (
          <span
            title="Save the strategy to run a backtest"
            className="flex items-center gap-1.5 border-2 border-ink bg-paper px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-wide text-ink/40"
          >
            <Play className="h-3 w-3 fill-current" /> Backtest
          </span>
        )}
      </div>

      {showLeaveConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-ink/40" onClick={() => !savingAndExiting && setShowLeaveConfirm(false)} />
          <div className="relative mx-4 w-full max-w-sm overflow-hidden border-2 border-ink bg-paper shadow-lg">
            <div className="p-5">
              <h2 className="font-display text-lg uppercase tracking-tight text-ink">Save changes?</h2>
              <p className="mt-1 text-sm text-ink/60">Your changes will be lost if you do not save them.</p>
            </div>
            <div className="flex border-t-2 border-ink">
              <button
                onClick={() => {
                  setShowLeaveConfirm(false);
                  navigate('/strategies');
                }}
                disabled={savingAndExiting}
                className="flex-1 border-r-2 border-ink px-4 py-3 text-sm font-medium text-red-600 transition-colors hover:bg-bone disabled:opacity-50"
              >
                Discard
              </button>
              <button
                onClick={() => setShowLeaveConfirm(false)}
                disabled={savingAndExiting}
                className="flex-1 border-r-2 border-ink px-4 py-3 text-sm font-medium text-ink/70 transition-colors hover:bg-bone disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveAndExit}
                disabled={savingAndExiting}
                className="flex flex-1 items-center justify-center gap-1.5 px-4 py-3 text-sm font-medium text-orange-600 transition-colors hover:bg-bone disabled:opacity-50"
              >
                {savingAndExiting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
