import { ArrowLeft, ChevronDown, Eye, Redo2, Share2, Trash2, Undo2, Loader2, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { StrategyType } from '../../../types/strategy';
import { Select } from '../../Select';

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

const TYPE_OPTIONS: { value: StrategyType; label: string }[] = [
  { value: 'trend_following', label: 'Trend Following' },
  { value: 'mean_reversion', label: 'Mean Reversion' },
  { value: 'momentum', label: 'Momentum' },
  { value: 'breakout', label: 'Breakout' },
  { value: 'custom', label: 'Custom' },
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
    // Metadata
    strategyName,
    strategyDescription,
    strategyType,
    timeframe,
    isDirty,
    setStrategyName,
    setStrategyDescription,
    setStrategyType,
    setTimeframe,
    // Async
    saving,
    error,
    saveStrategy,
    clearError,
  } = useStrategyBuilderStore();
  const [isDetailsOpen, setIsDetailsOpen] = useState(true);

  const selectedBlock = ui.selectedBlockId ? getBlock(ui.selectedBlockId) : null;
  const canDelete = selectedBlock && selectedBlock.type !== 'root';

  const handleSave = async () => {
    const savedId = await saveStrategy();
    if (savedId) {
      // Navigate to the saved strategy (in case it was new)
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
      {/* Error Banner */}
      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
            <button
              onClick={clearError}
              className="text-xs text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 mt-1"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Back + Save */}
      <div className="flex gap-2">
        <button
          onClick={() => navigate('/strategies')}
          className="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 transition-colors"
          title="Back to Strategies"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className={`flex-1 font-medium py-2.5 px-4 rounded-lg flex items-center justify-center gap-2 transition-all shadow-sm bg-primary-600 text-white ${
            saving || !isDirty
              ? 'opacity-50'
              : 'hover:bg-primary-700'
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

      {/* Undo/Redo/Delete */}
      <div className="flex gap-2">
        <button
          onClick={() => undo()}
          disabled={!canUndo()}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg border transition-colors ${
            canUndo()
              ? 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 shadow-sm'
              : 'bg-white/50 dark:bg-gray-900/50 border-gray-100 dark:border-gray-800 text-gray-300 dark:text-gray-600 cursor-not-allowed'
          }`}
          title="Undo (Cmd+Z)"
        >
          <Undo2 className="w-4 h-4" />
          <span className="text-xs">Undo</span>
        </button>
        <button
          onClick={() => redo()}
          disabled={!canRedo()}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg border transition-colors ${
            canRedo()
              ? 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 shadow-sm'
              : 'bg-white/50 dark:bg-gray-900/50 border-gray-100 dark:border-gray-800 text-gray-300 dark:text-gray-600 cursor-not-allowed'
          }`}
          title="Redo (Cmd+Shift+Z)"
        >
          <Redo2 className="w-4 h-4" />
          <span className="text-xs">Redo</span>
        </button>
        <button
          onClick={() => ui.selectedBlockId && deleteBlock(ui.selectedBlockId)}
          disabled={!canDelete}
          className={`flex items-center justify-center p-2 rounded-lg border transition-colors ${
            canDelete
              ? 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 hover:border-red-200 dark:hover:border-red-800 text-red-600 dark:text-red-400 shadow-sm'
              : 'bg-white/50 dark:bg-gray-900/50 border-gray-100 dark:border-gray-800 text-gray-300 dark:text-gray-600 cursor-not-allowed'
          }`}
          title="Delete selected (Del)"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Strategy Details */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
        <button
          onClick={() => setIsDetailsOpen(!isDetailsOpen)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Strategy Details</span>
          <ChevronDown
            className={`w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform ${
              isDetailsOpen ? '' : '-rotate-90'
            }`}
          />
        </button>

        {isDetailsOpen && (
          <div className="px-4 pb-4 space-y-4">
            {/* Name */}
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={strategyName}
                onChange={handleNameChange}
                className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Description</label>
              <textarea
                placeholder="Describe your strategy..."
                value={strategyDescription}
                onChange={handleDescriptionChange}
                rows={3}
                className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none resize-none"
              />
            </div>

            {/* Strategy Type */}
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Strategy Type
              </label>
              <Select
                value={strategyType}
                onChange={(e) => setStrategyType(e.target.value as StrategyType)}
                options={TYPE_OPTIONS}
              />
            </div>

            {/* Timeframe */}
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
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

      {/* Actions */}
      <div className="flex gap-2">
        <button className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 transition-colors shadow-sm">
          <Eye className="w-4 h-4" />
          <span className="text-sm">Watch</span>
        </button>
        <button className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 transition-colors shadow-sm">
          <Share2 className="w-4 h-4" />
          <span className="text-sm">Share</span>
        </button>
      </div>
    </div>
  );
}
