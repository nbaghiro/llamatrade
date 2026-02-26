import { ChevronDown, Eye, Redo2, Share2, Trash2, Undo2 } from 'lucide-react';
import { useState } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { RootBlock } from '../../../types/strategy-builder';
import { Select } from '../../Select';

export function LeftPanel() {
  const { tree, ui, updateBlock, undo, redo, canUndo, canRedo, deleteBlock, getBlock } =
    useStrategyBuilderStore();
  const rootBlock = tree.blocks[tree.rootId] as RootBlock;
  const [isDetailsOpen, setIsDetailsOpen] = useState(true);

  const selectedBlock = ui.selectedBlockId ? getBlock(ui.selectedBlockId) : null;
  const canDelete = selectedBlock && selectedBlock.type !== 'root';

  return (
    <div className="w-[320px] flex-shrink-0 flex flex-col gap-3 p-4 overflow-y-auto">
      {/* Save Button */}
      <button className="w-full bg-primary-600 hover:bg-primary-700 text-white font-medium py-2.5 px-4 rounded-lg flex items-center justify-center gap-2 transition-colors shadow-sm">
        <span className="text-sm">Save changes</span>
      </button>

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
                value={rootBlock.name}
                onChange={(e) => updateBlock(tree.rootId, { name: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Description</label>
              <textarea
                placeholder="Describe your strategy..."
                rows={3}
                className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none resize-none"
              />
            </div>

            {/* Trading Frequency */}
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Trading Frequency
              </label>
              <Select
                defaultValue="daily"
                options={[
                  { value: 'daily', label: 'Daily' },
                  { value: 'weekly', label: 'Weekly' },
                  { value: 'monthly', label: 'Monthly' },
                  { value: 'quarterly', label: 'Quarterly' },
                ]}
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
