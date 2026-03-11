import { ChevronDown, ChevronRight, Layers } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import type { GroupBlock as GroupBlockType } from '../../../types/strategy-builder';
import { useBlockTheme } from '../useTheme';

interface GroupBlockProps {
  block: GroupBlockType;
  allocationPercent?: number;
  readOnly?: boolean;
}

export function GroupBlock({ block, allocationPercent, readOnly }: GroupBlockProps) {
  const { ui, selectBlock, toggleExpand, setEditing, updateBlock } = useStrategyBuilderStoreWithContext();
  const theme = useBlockTheme();
  const groupColors = theme.group;
  const allocationBadgeColors = theme.allocation;
  const isSelected = !readOnly && ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);
  const isEditing = !readOnly && ui.editingBlockId === block.id;
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
    if (!readOnly) {
      selectBlock(block.id);
    }
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!readOnly) {
      setEditValue(block.name);
      setEditing(block.id);
    }
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
        flex items-center gap-3 px-4 py-3 rounded-lg border ${groupColors.bg}
        transition-all duration-150 select-none
        ${readOnly ? 'cursor-default' : 'cursor-pointer'}
        ${isSelected ? `${groupColors.borderSelected} ${groupColors.ringSelected}` : `${groupColors.border} ${readOnly ? '' : groupColors.borderHover}`}
      `}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      {/* Percentage badge for specified weight children */}
      {allocationPercent !== undefined && (
        <span className={`px-2 py-0.5 text-xs font-semibold ${allocationBadgeColors.bg} ${allocationBadgeColors.text} rounded`}>
          {allocationPercent}%
        </span>
      )}

      <button onClick={handleExpandClick} className={`p-0.5 ${groupColors.expandHover} rounded`}>
        {isExpanded ? (
          <ChevronDown className={`w-4 h-4 ${groupColors.textMuted}`} />
        ) : (
          <ChevronRight className={`w-4 h-4 ${groupColors.textMuted}`} />
        )}
      </button>

      <Layers className={`w-4 h-4 ${groupColors.icon}`} />

      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          className={`flex-1 font-medium ${groupColors.text} bg-amber-50 dark:bg-amber-900/30 px-2 py-0.5 rounded border border-amber-300 dark:border-amber-700 outline-none`}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className={`flex-1 font-medium ${groupColors.text}`}>{block.name}</span>
      )}
    </div>
  );
}
