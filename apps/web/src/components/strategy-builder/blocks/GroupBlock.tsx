import { ChevronDown, ChevronRight, Layers } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { GroupBlock as GroupBlockType } from '../../../types/strategy-builder';

interface GroupBlockProps {
  block: GroupBlockType;
  allocationPercent?: number;
}

export function GroupBlock({ block, allocationPercent }: GroupBlockProps) {
  const { ui, selectBlock, toggleExpand, setEditing, updateBlock } = useStrategyBuilderStore();
  const isSelected = ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);
  const isEditing = ui.editingBlockId === block.id;
  const inputRef = useRef<HTMLInputElement>(null);
  const [editValue, setEditValue] = useState(block.name);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectBlock(block.id);
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditValue(block.name);
    setEditing(block.id);
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleExpand(block.id);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      updateBlock(block.id, { name: editValue.trim() || 'Unnamed Group' });
      setEditing(null);
    } else if (e.key === 'Escape') {
      setEditing(null);
    }
  };

  const handleBlur = () => {
    if (isEditing) {
      updateBlock(block.id, { name: editValue.trim() || 'Unnamed Group' });
      setEditing(null);
    }
  };

  return (
    <div
      className={`
        flex items-center gap-3 px-4 py-3 rounded-lg border bg-white dark:bg-gray-900 cursor-pointer
        transition-all duration-150 select-none
        ${isSelected ? 'border-blue-500 ring-2 ring-blue-500/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'}
      `}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className="px-2 py-0.5 text-xs font-semibold bg-blue-500 text-white rounded">
          {allocationPercent}%
        </span>
      )}

      <button onClick={handleExpandClick} className="p-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-gray-500 dark:text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500 dark:text-gray-400" />
        )}
      </button>

      <Layers className="w-4 h-4 text-gray-400" />

      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          className="flex-1 font-medium text-gray-900 dark:text-gray-100 bg-blue-50 dark:bg-blue-900/30 px-2 py-0.5 rounded border border-blue-300 dark:border-blue-700 outline-none"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className="flex-1 font-medium text-gray-900 dark:text-gray-100">{block.name}</span>
      )}
    </div>
  );
}
