import type { BlockId } from '@llamatrade/core/strategy/types';
import { useState, useRef, useEffect } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';

interface PercentageBadgeProps {
  weightBlockId: BlockId;
  childBlockId: BlockId;
}

export function PercentageBadge({ weightBlockId, childBlockId }: PercentageBadgeProps) {
  const { tree, setWeightAllocation } = useStrategyBuilderStoreWithContext();
  const weightBlock = tree.blocks[weightBlockId];
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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
        onClick={(e) => e.stopPropagation()}
        className="w-14 flex-none border-2 border-ink bg-paper px-1 text-center font-mono text-[11px] font-bold tabular-nums text-ink outline-none"
      />
    );
  }

  return (
    <button
      onClick={handleClick}
      className={`flex-none cursor-pointer border-2 border-ink px-2 font-mono text-[11px] font-bold leading-[1.5] tabular-nums transition-colors ${
        allocation > 0 ? 'bg-ink text-bone hover:bg-ink/80' : 'bg-paper text-ink/60 hover:bg-bone'
      }`}
    >
      {allocation > 0 ? `${allocation}%` : '0%'}
    </button>
  );
}
