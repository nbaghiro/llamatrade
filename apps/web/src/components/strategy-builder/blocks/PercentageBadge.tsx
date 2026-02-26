import { useState, useRef, useEffect } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { BlockId } from '../../../types/strategy-builder';

interface PercentageBadgeProps {
  weightBlockId: BlockId;
  childBlockId: BlockId;
}

export function PercentageBadge({ weightBlockId, childBlockId }: PercentageBadgeProps) {
  const { tree, setWeightAllocation } = useStrategyBuilderStore();
  const weightBlock = tree.blocks[weightBlockId];
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Get current allocation or default to 0
  const allocation =
    weightBlock?.type === 'weight'
      ? weightBlock.allocations[childBlockId] ?? 0
      : 0;

  const [editValue, setEditValue] = useState(String(allocation));

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  useEffect(() => {
    setEditValue(String(allocation));
  }, [allocation]);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      const value = parseFloat(editValue) || 0;
      setWeightAllocation(weightBlockId, childBlockId, value);
      setIsEditing(false);
    } else if (e.key === 'Escape') {
      setEditValue(String(allocation));
      setIsEditing(false);
    }
  };

  const handleBlur = () => {
    const value = parseFloat(editValue) || 0;
    setWeightAllocation(weightBlockId, childBlockId, value);
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <div className="absolute -top-2 -right-2 z-10">
        <input
          ref={inputRef}
          type="number"
          min="0"
          max="100"
          step="0.1"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          className="w-14 px-1 py-0.5 text-xs font-medium text-center bg-white dark:bg-gray-800 border-2 border-blue-500 rounded shadow-sm outline-none"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    );
  }

  return (
    <button
      onClick={handleClick}
      className={`
        absolute -top-2 -right-2 z-10 px-2 py-0.5 text-xs font-medium rounded-full
        shadow-sm cursor-pointer transition-colors
        ${allocation > 0
          ? 'bg-blue-500 text-white hover:bg-blue-600'
          : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-300 dark:hover:bg-gray-600'}
      `}
    >
      {allocation > 0 ? `${allocation}%` : '0%'}
    </button>
  );
}
