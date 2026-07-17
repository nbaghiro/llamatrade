import { Scale } from 'lucide-react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { BlockId, WeightMethod } from '@llamatrade/core/strategy/types';
import { WEIGHT_METHODS } from '@llamatrade/core/strategy/types';

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
          className="group w-full flex items-center gap-3 px-3 py-2 hover:bg-ink transition-colors"
        >
          <div className={`p-1.5 ${info.color.bg} border-2 border-ink`}>
            <Scale className={`w-4 h-4 ${info.color.text}`} />
          </div>
          <div className="flex-1 text-left">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-ink group-hover:text-bone">
                {info.label}
              </span>
              {info.hasLookback && (
                <span className="px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide border border-ink text-ink/70 group-hover:border-bone group-hover:text-bone">
                  lookback
                </span>
              )}
            </div>
            <div className="text-xs text-ink/60 group-hover:text-bone">{info.description}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
