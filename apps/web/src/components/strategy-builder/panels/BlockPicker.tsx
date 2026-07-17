import type { BlockId, ConditionExpression, FilterConfig } from '@llamatrade/core/strategy/types';
import { TrendingUp, Folder, Scale, ArrowLeft, GitBranch, Filter } from 'lucide-react';
import { useState } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import { useBlockTheme } from '../useTheme';

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
  const theme = useBlockTheme();
  const pickerColors = theme.picker;
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
        <div className="bg-paper border-2 border-ink shadow-lg min-w-[280px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b-2 border-ink bg-bone">
            <button
              onClick={() => setView('main')}
              className="p-1 hover:bg-ink/10"
            >
              <ArrowLeft className="w-4 h-4 text-ink/60" />
            </button>
            <span className="text-[11px] font-mono uppercase tracking-wide text-ink/70">Add Asset</span>
          </div>
          <AssetPicker parentId={parentId} onClose={onClose} />
        </div>
      </div>
    );
  }

  if (view === 'weight') {
    return (
      <div className="absolute top-full left-0 mt-2 z-20">
        <div className="bg-paper border-2 border-ink shadow-lg min-w-[280px]">
          <div className="flex items-center gap-2 px-3 py-2 border-b-2 border-ink bg-bone">
            <button
              onClick={() => setView('main')}
              className="p-1 hover:bg-ink/10"
            >
              <ArrowLeft className="w-4 h-4 text-ink/60" />
            </button>
            <span className="text-[11px] font-mono uppercase tracking-wide text-ink/70">Choose Weight Method</span>
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
      <div className="bg-paper border-2 border-ink shadow-lg min-w-[200px]">
        <div className="px-3 py-2 border-b-2 border-ink bg-bone">
          <span className="text-[11px] font-mono uppercase tracking-wide text-ink/70">Add Block</span>
        </div>
        <div className="p-2">
          <button
            onClick={() => setView('asset')}
            className="group w-full flex items-center gap-3 px-3 py-2 hover:bg-ink transition-colors"
          >
            <div className={`p-1.5 ${pickerColors.asset.bg} rounded`}>
              <TrendingUp className={`w-4 h-4 ${pickerColors.asset.icon}`} />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink group-hover:text-bone">Asset</div>
              <div className="text-xs text-ink/60 group-hover:text-bone">Stock, ETF, or crypto</div>
            </div>
          </button>

          <button
            onClick={() => {
              addGroup(parentId, 'New Group');
              onClose();
            }}
            className="group w-full flex items-center gap-3 px-3 py-2 hover:bg-ink transition-colors"
          >
            <div className={`p-1.5 ${pickerColors.group.bg} rounded`}>
              <Folder className={`w-4 h-4 ${pickerColors.group.icon}`} />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink group-hover:text-bone">Group</div>
              <div className="text-xs text-ink/60 group-hover:text-bone">Container for organizing</div>
            </div>
          </button>

          <button
            onClick={() => setView('weight')}
            className="group w-full flex items-center gap-3 px-3 py-2 hover:bg-ink transition-colors"
          >
            <div className={`p-1.5 ${pickerColors.weight.bg} rounded`}>
              <Scale className={`w-4 h-4 ${pickerColors.weight.icon}`} />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink group-hover:text-bone">Weight</div>
              <div className="text-xs text-ink/60 group-hover:text-bone">Allocation method</div>
            </div>
          </button>

          <div className="my-2 border-t-2 border-ink/15" />

          <button
            onClick={() => setView('condition')}
            className="group w-full flex items-center gap-3 px-3 py-2 hover:bg-ink transition-colors"
          >
            <div className={`p-1.5 ${pickerColors.ifElse.bg} rounded`}>
              <GitBranch className={`w-4 h-4 ${pickerColors.ifElse.icon}`} />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink group-hover:text-bone">If/Else</div>
              <div className="text-xs text-ink/60 group-hover:text-bone">Conditional allocation</div>
            </div>
          </button>

          <button
            onClick={() => setView('filter')}
            className="group w-full flex items-center gap-3 px-3 py-2 hover:bg-ink transition-colors"
          >
            <div className={`p-1.5 ${pickerColors.filter.bg} rounded`}>
              <Filter className={`w-4 h-4 ${pickerColors.filter.icon}`} />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink group-hover:text-bone">Filter</div>
              <div className="text-xs text-ink/60 group-hover:text-bone">Dynamic asset selection</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
