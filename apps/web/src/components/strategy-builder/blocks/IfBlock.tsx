import { conditionToText } from '@llamatrade/core/strategy/serializer';
import type { IfBlock as IfBlockType, ConditionExpression } from '@llamatrade/core/strategy/types';
import { ChevronDown, Pencil, X } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { ConditionEditor } from '../panels/ConditionEditor';
import { useBlockTheme } from '../useTheme';

interface IfBlockProps {
  block: IfBlockType;
  allocationPercent?: number;
  readOnly?: boolean;
}

export function IfBlock({ block, readOnly }: IfBlockProps) {
  const { ui, selectBlock, toggleExpand, updateCondition, deleteBlock, tree } = useStrategyBuilderStoreWithContext();
  const theme = useBlockTheme();
  const isSelected = !readOnly && ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);
  const [isEditing, setIsEditing] = useState(false);
  const blockRef = useRef<HTMLDivElement>(null);

  const displayText = conditionToText(block.condition);

  const firstSymbol = Object.values(tree.blocks).find(b => b.type === 'asset')?.symbol || 'SPY';

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!readOnly) {
      selectBlock(block.id);
    }
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleExpand(block.id);
  };

  const handleEditClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!readOnly) {
      setIsEditing(true);
    }
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteBlock(block.id);
  };

  const handleSaveCondition = (condition: ConditionExpression) => {
    updateCondition(block.id, condition);
    setIsEditing(false);
  };

  useEffect(() => {
    if (!isEditing) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (blockRef.current && !blockRef.current.contains(e.target as Node)) {
        setIsEditing(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditing]);

  const colors = theme.ifBlock;

  return (
    <div ref={blockRef} className="relative">
      <div
        data-testid="if-block"
        className={`
          inline-flex items-center gap-1.5 py-1.5
          transition-all duration-150 select-none
          ${colors.bg} text-sm
          ${readOnly ? 'cursor-default pl-3 pr-3' : 'cursor-pointer pl-1.5 pr-3'}
          ${isSelected ? `ring-2 ${colors.ring} ring-offset-2 ring-offset-bone` : readOnly ? '' : colors.hover}
        `}
        onClick={handleClick}
      >
        {!readOnly && (
          <button
            onClick={handleDeleteClick}
            className={`p-0.5 rounded-full ${colors.hover} transition-colors`}
            title="Delete"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}

        <button
          onClick={handleExpandClick}
          className={`p-0.5 rounded-full ${colors.hover} transition-colors`}
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>

        <span className="font-mono font-bold tracking-wide">IF</span>
        <span className="font-normal opacity-90">{displayText}</span>

        {!readOnly && (
          <button
            onClick={handleEditClick}
            className={`p-0.5 rounded-full ${colors.hover} transition-colors ml-1`}
            title="Edit condition"
          >
            <Pencil className="w-3 h-3" />
          </button>
        )}
      </div>

      {isEditing && (
        <div className="absolute left-0 top-full mt-2 z-50">
          <ConditionEditor
            condition={block.condition}
            defaultSymbol={firstSymbol}
            onSave={handleSaveCondition}
            onCancel={() => setIsEditing(false)}
          />
        </div>
      )}
    </div>
  );
}
