import { TrendingUp, Folder, Scale, ArrowLeft } from 'lucide-react';
import { useState } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { BlockId } from '../../../types/strategy-builder';

import { AssetPicker } from './AssetPicker';
import { WeightMethodPicker } from './WeightMethodPicker';

type PickerView = 'main' | 'asset' | 'weight';

interface BlockPickerProps {
  parentId: BlockId;
  onClose: () => void;
}

export function BlockPicker({ parentId, onClose }: BlockPickerProps) {
  const [view, setView] = useState<PickerView>('main');
  const addGroup = useStrategyBuilderStore((s) => s.addGroup);

  if (view === 'asset') {
    return (
      <div className="absolute top-full left-0 mt-2 z-20">
        <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden min-w-[280px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800">
            <button
              onClick={() => setView('main')}
              className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
            >
              <ArrowLeft className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Add Asset</span>
          </div>
          <AssetPicker parentId={parentId} onClose={onClose} />
        </div>
      </div>
    );
  }

  if (view === 'weight') {
    return (
      <div className="absolute top-full left-0 mt-2 z-20">
        <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden min-w-[280px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800">
            <button
              onClick={() => setView('main')}
              className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
            >
              <ArrowLeft className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Choose Weight Method</span>
          </div>
          <WeightMethodPicker parentId={parentId} onClose={onClose} />
        </div>
      </div>
    );
  }

  return (
    <div className="absolute top-full left-0 mt-2 z-20">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden min-w-[200px]">
        <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Add Block</span>
        </div>
        <div className="p-2">
          <button
            onClick={() => setView('asset')}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div className="p-1.5 bg-emerald-100 dark:bg-emerald-900/30 rounded">
              <TrendingUp className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Asset</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Stock, ETF, or crypto</div>
            </div>
          </button>

          <button
            onClick={() => {
              addGroup(parentId, 'New Group');
              onClose();
            }}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div className="p-1.5 bg-amber-100 dark:bg-amber-900/30 rounded">
              <Folder className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Group</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Container for organizing</div>
            </div>
          </button>

          <button
            onClick={() => setView('weight')}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div className="p-1.5 bg-blue-100 dark:bg-blue-900/30 rounded">
              <Scale className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Weight</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Allocation method</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
