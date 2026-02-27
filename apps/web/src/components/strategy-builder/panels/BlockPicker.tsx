import { TrendingUp, Folder, Scale, ArrowLeft, GitBranch, Filter } from 'lucide-react';
import { useState } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { BlockId, ConditionExpression, FilterConfig } from '../../../types/strategy-builder';

import { AssetPicker } from './AssetPicker';
import { ConditionBuilder } from './ConditionBuilder';
import { FilterBuilder } from './FilterBuilder';
import { WeightMethodPicker } from './WeightMethodPicker';

type PickerView = 'main' | 'asset' | 'weight' | 'condition' | 'filter';

interface BlockPickerProps {
  parentId: BlockId;
  onClose: () => void;
}

export function BlockPicker({ parentId, onClose }: BlockPickerProps) {
  const [view, setView] = useState<PickerView>('main');
  const addGroup = useStrategyBuilderStore((s) => s.addGroup);
  const addCondition = useStrategyBuilderStore((s) => s.addCondition);
  const addFilter = useStrategyBuilderStore((s) => s.addFilter);

  const handleConditionSave = (condition: ConditionExpression) => {
    addCondition(parentId, condition);
    onClose();
  };

  const handleFilterSave = (config: FilterConfig) => {
    addFilter(parentId, config);
    onClose();
  };

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

  if (view === 'condition') {
    return (
      <div className="absolute top-full left-0 mt-2 z-20">
        <ConditionBuilder
          onSave={handleConditionSave}
          onCancel={() => setView('main')}
        />
      </div>
    );
  }

  if (view === 'filter') {
    return (
      <div className="absolute top-full left-0 mt-2 z-20">
        <FilterBuilder
          onSave={handleFilterSave}
          onCancel={() => setView('main')}
        />
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

          <div className="my-2 border-t border-gray-100 dark:border-gray-800" />

          <button
            onClick={() => setView('condition')}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div className="p-1.5 bg-amber-100 dark:bg-amber-900/30 rounded">
              <GitBranch className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">If/Else</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Conditional allocation</div>
            </div>
          </button>

          <button
            onClick={() => setView('filter')}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div className="p-1.5 bg-purple-100 dark:bg-purple-900/30 rounded">
              <Filter className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Filter</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Dynamic asset selection</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
