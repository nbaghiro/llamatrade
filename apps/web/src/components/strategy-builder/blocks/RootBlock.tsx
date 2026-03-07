import { ChevronDown, ChevronRight, Code2, GitBranch, Layers } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useStrategyBuilderStore, type ViewMode } from '../../../store/strategy-builder';
import type { RootBlock as RootBlockType } from '../../../types/strategy-builder';

interface RootBlockProps {
  block: RootBlockType;
}

interface ViewButtonProps {
  mode: ViewMode;
  currentMode: ViewMode;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}

function ViewButton({ mode, currentMode, icon, label, onClick }: ViewButtonProps) {
  const isActive = mode === currentMode;

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title={label}
      aria-label={label}
      className={`
        p-1.5 rounded transition-colors
        ${isActive
          ? 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
          : 'text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-600 dark:hover:text-gray-300'
        }
      `}
    >
      {icon}
    </button>
  );
}

export function RootBlock({ block }: RootBlockProps) {
  const { ui, viewMode, setViewMode, selectBlock, toggleExpand, setEditing, updateBlock } = useStrategyBuilderStore();
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
      updateBlock(block.id, { name: editValue.trim() || 'My Strategy' });
      setEditing(null);
    } else if (e.key === 'Escape') {
      setEditing(null);
    }
  };

  const handleBlur = () => {
    if (isEditing) {
      updateBlock(block.id, { name: editValue.trim() || 'My Strategy' });
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
      <button onClick={handleExpandClick} className="p-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-gray-500 dark:text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500 dark:text-gray-400" />
        )}
      </button>

      <div className="p-1.5 bg-gray-100 dark:bg-gray-800 rounded">
        <Layers className="w-4 h-4 text-gray-600 dark:text-gray-400" />
      </div>

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

      {/* View Switcher */}
      <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
        <ViewButton
          mode="tree"
          currentMode={viewMode}
          icon={<GitBranch size={14} />}
          label="Visual Editor"
          onClick={() => setViewMode('tree')}
        />
        <ViewButton
          mode="code"
          currentMode={viewMode}
          icon={<Code2 size={14} />}
          label="Code Editor"
          onClick={() => setViewMode('code')}
        />
      </div>
    </div>
  );
}
