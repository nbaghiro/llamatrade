import { ArrowLeft, ChevronDown, Eye, Redo2, Share2, Trash2, Undo2, Loader2, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
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

export function LeftPanel() {
  const navigate = useNavigate();
  const {
    ui,
    undo,
    redo,
    canUndo,
    canRedo,
    deleteBlock,
    getBlock,
    strategyId,
    strategyName,
    strategyDescription,
    timeframe,
    isDirty,
    setStrategyName,
    setStrategyDescription,
    setTimeframe,
    saving,
    error,
    saveStrategy,
    clearError,
  } = useStrategyBuilderStore();
  const [isDetailsOpen, setIsDetailsOpen] = useState(true);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);
  const [savingAndExiting, setSavingAndExiting] = useState(false);

  const selectedBlock = ui.selectedBlockId ? getBlock(ui.selectedBlockId) : null;
  const canDelete = selectedBlock && selectedBlock.type !== 'root';

  const handleBack = () => {
    if (isDirty) {
      setShowLeaveConfirm(true);
    } else {
      navigate('/strategies');
    }
  };

  const handleDiscard = () => {
    setShowLeaveConfirm(false);
    navigate('/strategies');
  };

  const handleSaveAndExit = async () => {
    setSavingAndExiting(true);
    const savedId = await saveStrategy();
    setSavingAndExiting(false);
    if (savedId) {
      setShowLeaveConfirm(false);
      navigate('/strategies');
    }
    // If save failed, keep dialog open so user can see error
  };

  const handleSave = async () => {
    const wasNew = !strategyId;
    const savedId = await saveStrategy();
    if (savedId && wasNew) {
      // Only navigate when creating a new strategy, not when updating
      navigate(`/strategies/${savedId}`, { replace: true });
    }
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setStrategyName(e.target.value);
  };

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setStrategyDescription(e.target.value);
  };

  return (
    <div className="w-[320px] flex-shrink-0 flex flex-col gap-3 p-4 overflow-y-auto">
      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border-2 border-ink">
          <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-red-700">{error}</p>
            <button
              onClick={clearError}
              className="text-xs text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 mt-1"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleBack}
          className="p-1.5 border-2 border-ink bg-paper text-ink hover:bg-ink hover:text-bone transition-colors"
          title={strategyId ? 'Back to Strategies' : 'Back to Templates'}
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className={`flex-1 font-mono font-bold uppercase tracking-wide py-2.5 px-4 flex items-center justify-center gap-2 transition-all shadow bg-orange-500 text-bone border-2 border-ink ${
            saving || !isDirty
              ? 'opacity-50'
              : 'hover:bg-orange-600'
          }`}
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Saving...</span>
            </>
          ) : (
            <span className="text-sm">Save changes</span>
          )}
        </button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => undo()}
          disabled={!canUndo()}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-2 border-2 transition-colors ${
            canUndo()
              ? 'bg-paper border-ink hover:bg-ink hover:text-bone text-ink'
              : 'bg-paper border-ink/30 text-ink/30 cursor-not-allowed'
          }`}
          title="Undo (Cmd+Z)"
        >
          <Undo2 className="w-4 h-4" />
          <span className="text-xs">Undo</span>
        </button>
        <button
          onClick={() => redo()}
          disabled={!canRedo()}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-2 border-2 transition-colors ${
            canRedo()
              ? 'bg-paper border-ink hover:bg-ink hover:text-bone text-ink'
              : 'bg-paper border-ink/30 text-ink/30 cursor-not-allowed'
          }`}
          title="Redo (Cmd+Shift+Z)"
        >
          <Redo2 className="w-4 h-4" />
          <span className="text-xs">Redo</span>
        </button>
        <button
          onClick={() => ui.selectedBlockId && deleteBlock(ui.selectedBlockId)}
          disabled={!canDelete}
          className={`flex items-center justify-center p-2 border-2 transition-colors ${
            canDelete
              ? 'bg-paper border-ink hover:bg-red-500 hover:text-bone text-red-600'
              : 'bg-paper border-ink/30 text-ink/30 cursor-not-allowed'
          }`}
          title="Delete selected (Del)"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="bg-paper border-2 border-ink shadow">
        <button
          onClick={() => setIsDetailsOpen(!isDetailsOpen)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-ink/5 transition-colors"
        >
          <span className="text-[11px] font-mono uppercase tracking-wide text-ink/70">Strategy Details</span>
          <ChevronDown
            className={`w-4 h-4 text-ink/60 transition-transform ${
              isDetailsOpen ? '' : '-rotate-90'
            }`}
          />
        </button>

        {isDetailsOpen && (
          <div className="px-4 pb-4 space-y-4">
            <div>
              <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">Name</label>
              <input
                type="text"
                value={strategyName}
                onChange={handleNameChange}
                className="w-full px-3 py-2 text-sm border-2 border-ink bg-paper text-ink focus:border-orange-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">Description</label>
              <textarea
                placeholder="Describe your strategy..."
                value={strategyDescription}
                onChange={handleDescriptionChange}
                rows={3}
                className="w-full px-3 py-2 text-sm border-2 border-ink bg-paper text-ink placeholder:text-ink/40 focus:border-orange-500 outline-none resize-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-1">
                Timeframe
              </label>
              <Select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                options={TIMEFRAME_OPTIONS}
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button className="flex-1 flex items-center justify-center gap-2 py-2 px-3 border-2 border-ink bg-paper hover:bg-ink hover:text-bone text-ink transition-colors">
          <Eye className="w-4 h-4" />
          <span className="text-sm">Watch</span>
        </button>
        <button className="flex-1 flex items-center justify-center gap-2 py-2 px-3 border-2 border-ink bg-paper hover:bg-ink hover:text-bone text-ink transition-colors">
          <Share2 className="w-4 h-4" />
          <span className="text-sm">Share</span>
        </button>
      </div>

      {showLeaveConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-ink/40"
            onClick={() => !savingAndExiting && setShowLeaveConfirm(false)}
          />
          <div className="relative bg-paper border-2 border-ink shadow-lg max-w-sm w-full mx-4 overflow-hidden">
            <div className="p-5">
              <h2 className="font-display text-lg uppercase tracking-tight text-ink">
                Save changes?
              </h2>
              <p className="text-sm text-ink/60 mt-1">
                Your changes will be lost if you do not save them.
              </p>
            </div>
            <div className="flex border-t-2 border-ink">
              <button
                onClick={handleDiscard}
                disabled={savingAndExiting}
                className="flex-1 px-4 py-3 text-sm font-medium text-red-600 hover:bg-bone disabled:opacity-50 transition-colors border-r-2 border-ink"
              >
                Discard
              </button>
              <button
                onClick={() => setShowLeaveConfirm(false)}
                disabled={savingAndExiting}
                className="flex-1 px-4 py-3 text-sm font-medium text-ink/70 hover:bg-bone disabled:opacity-50 transition-colors border-r-2 border-ink"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveAndExit}
                disabled={savingAndExiting}
                className="flex-1 px-4 py-3 text-sm font-medium text-orange-600 hover:bg-bone disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
              >
                {savingAndExiting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  'Save'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
