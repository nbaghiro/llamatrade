import { ChevronDown, Pencil, X } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

import { conditionToText } from '../../../services/strategy-serializer';
import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { IfBlock as IfBlockType, ConditionExpression } from '../../../types/strategy-builder';
import { getIfColors } from '../block-theme';
import { ConditionEditor } from '../panels/ConditionEditor';

interface IfBlockProps {
  block: IfBlockType;
  allocationPercent?: number;
}

export function IfBlock({ block }: IfBlockProps) {
  const { ui, selectBlock, toggleExpand, updateCondition, deleteBlock, tree } = useStrategyBuilderStore();
  const isSelected = ui.selectedBlockId === block.id;
  const isExpanded = ui.expandedBlocks.has(block.id);
  const [isEditing, setIsEditing] = useState(false);
  const blockRef = useRef<HTMLDivElement>(null);

  // Get fresh condition text
  const displayText = conditionToText(block.condition);

  // Get first symbol from strategy for default
  const firstSymbol = Object.values(tree.blocks).find(b => b.type === 'asset')?.symbol || 'SPY';

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectBlock(block.id);
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleExpand(block.id);
  };

  const handleEditClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteBlock(block.id);
  };

  const handleSaveCondition = (condition: ConditionExpression) => {
    updateCondition(block.id, condition);
    setIsEditing(false);
  };

  // Close editor when clicking outside
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

  // Determine if condition uses indicators (vs pure price)
  const hasIndicator =
    block.condition.left.type === 'indicator' || block.condition.right.type === 'indicator';

  const colors = getIfColors(hasIndicator);

  return (
    <div ref={blockRef} className="relative">
      {/* Main pill - emerald for price, teal for indicator conditions */}
      <div
        data-testid="if-block"
        className={`
          inline-flex items-center gap-1.5 pl-1.5 pr-3 py-1.5 rounded-full cursor-pointer
          transition-all duration-150 select-none
          ${colors.bg} text-white text-sm
          ${isSelected ? `ring-2 ${colors.ring} ring-offset-2 ring-offset-white dark:ring-offset-gray-900` : colors.hover}
        `}
        onClick={handleClick}
      >
        {/* Delete button */}
        <button
          onClick={handleDeleteClick}
          className={`p-0.5 rounded-full ${colors.hover} transition-colors`}
          title="Delete"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        {/* Expand toggle */}
        <button
          onClick={handleExpandClick}
          className={`p-0.5 rounded-full ${colors.hover} transition-colors`}
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
        </button>

        {/* IF label and condition text */}
        <span className="font-semibold">IF</span>
        <span className="font-normal opacity-90">{displayText}</span>

        {/* Edit button */}
        <button
          onClick={handleEditClick}
          className={`p-0.5 rounded-full ${colors.hover} transition-colors ml-1`}
          title="Edit condition"
        >
          <Pencil className="w-3 h-3" />
        </button>
      </div>

      {/* Inline Condition Editor Popover */}
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
