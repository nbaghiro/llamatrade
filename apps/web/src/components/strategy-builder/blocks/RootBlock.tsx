import { ChevronDown, ChevronRight, Code2, Eye, GitBranch, Layers, Pencil } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useStrategyBuilderStoreWithContext, type ViewMode } from '../../../store/strategy-builder';
import type { RootBlock as RootBlockType } from '../../../types/strategy-builder';

interface RootBlockProps {
  block: RootBlockType;
  readOnly?: boolean;
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
        p-1.5 transition-colors
        ${isActive
          ? 'bg-ink text-bone'
          : 'text-ink/50 hover:bg-ink/10 hover:text-ink'
        }
      `}
    >
      {icon}
    </button>
  );
}

export function RootBlock({ block, readOnly }: RootBlockProps) {
  const { ui, viewMode, compactView, setViewMode, toggleCompactView, selectBlock, toggleExpand, setEditing, updateBlock } = useStrategyBuilderStoreWithContext();
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
        flex items-center gap-3 px-4 py-3 border-2 bg-paper
        transition-all duration-150 select-none
        ${readOnly ? 'cursor-default' : 'cursor-pointer'}
        ${isSelected ? 'border-orange-500 ring-2 ring-orange-500' : `border-ink ${readOnly ? '' : 'hover:border-ink'}`}
      `}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      <button onClick={handleExpandClick} className="p-0.5 hover:bg-ink/5">
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-ink/60" />
        ) : (
          <ChevronRight className="w-4 h-4 text-ink/60" />
        )}
      </button>

      <div className="p-1.5 bg-orange-500 border-2 border-ink">
        <Layers className="w-4 h-4 text-ink" />
      </div>

      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          className="font-display text-lg uppercase tracking-tight text-ink bg-bone px-2 py-0.5 border-2 border-ink outline-none"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className="font-display text-lg uppercase tracking-tight text-ink">{block.name}</span>
      )}

      {!readOnly && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleCompactView();
          }}
          title={compactView ? 'Switch to edit mode' : 'Switch to view mode'}
          className="p-1.5 border-2 border-ink bg-paper text-ink hover:bg-ink hover:text-bone transition-colors"
        >
          {compactView ? <Pencil size={14} /> : <Eye size={14} />}
        </button>
      )}

      <div className="flex-1" />

      <div className="flex items-center gap-0.5 border-2 border-ink bg-paper p-0.5">
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
