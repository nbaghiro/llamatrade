import { Scale } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { BlockId, WeightMethod } from '../../../types/strategy-builder';
import { WEIGHT_METHODS } from '../../../types/strategy-builder';

interface WeightMethodPickerProps {
  parentId: BlockId;
  onClose: () => void;
}

export function WeightMethodPicker({ parentId, onClose }: WeightMethodPickerProps) {
  const addWeight = useStrategyBuilderStore((s) => s.addWeight);

  const handleSelect = (method: WeightMethod) => {
    addWeight(parentId, method);
    onClose();
  };

  return (
    <div className="p-2 max-h-[320px] overflow-y-auto">
      {WEIGHT_METHODS.map((info) => (
        <button
          key={info.method}
          onClick={() => handleSelect(info.method)}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className={`p-1.5 ${info.color.bg} rounded`}>
            <Scale className={`w-4 h-4 ${info.color.text}`} />
          </div>
          <div className="flex-1 text-left">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {info.label}
              </span>
              {info.hasLookback && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded">
                  lookback
                </span>
              )}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">{info.description}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
