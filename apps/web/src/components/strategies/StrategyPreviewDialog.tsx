/**
 * Shows a preview of a strategy template before opening in the full editor.
 */

import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { BlockId } from '@llamatrade/core/strategy/types';
import { hasChildren } from '@llamatrade/core/strategy/types';
import { ArrowLeft, ArrowRight, X } from 'lucide-react';
import { useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
  TemplateCategory,
  TemplateDifficulty,
} from '../../data/strategy-templates';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import { useUIStore } from '../../store/ui';
import { StrategyBuilder } from '../strategy-builder/StrategyBuilder';

const DIFFICULTY_COLORS: Record<TemplateDifficulty, string> = {
  [TemplateDifficulty.UNSPECIFIED]: 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400',
  [TemplateDifficulty.BEGINNER]: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  [TemplateDifficulty.INTERMEDIATE]: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  [TemplateDifficulty.ADVANCED]: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

const CATEGORY_COLORS: Record<TemplateCategory, string> = {
  [TemplateCategory.UNSPECIFIED]: 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400',
  [TemplateCategory.BUY_AND_HOLD]: 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400',
  [TemplateCategory.TACTICAL]: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  [TemplateCategory.FACTOR]: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  [TemplateCategory.INCOME]: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  [TemplateCategory.TREND]: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  [TemplateCategory.MEAN_REVERSION]: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  [TemplateCategory.ALTERNATIVES]: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
};

export default function StrategyPreviewDialog() {
  const navigate = useNavigate();
  const { previewDialogOpen, previewTemplate, closePreviewDialog, closeAllStrategyDialogs } = useUIStore();

  // Load the template into the strategy builder store when preview opens
  useEffect(() => {
    if (!previewDialogOpen || !previewTemplate) return;

    const parseResult = fromDSLString(previewTemplate.config_sexpr);

    if (!parseResult) {
      // Fallback: create empty strategy with just the name if DSL parsing fails
      useStrategyBuilderStore.getState().createNew();
      useStrategyBuilderStore.setState({
        strategyName: previewTemplate.name,
        strategyDescription: previewTemplate.description,
      });
      return;
    }

    const { tree, metadata } = parseResult;

    const expandedBlocks = new Set<BlockId>();
    for (const block of Object.values(tree.blocks)) {
      if (hasChildren(block)) {
        expandedBlocks.add(block.id);
      }
    }

    useStrategyBuilderStore.setState({
      tree,
      ui: {
        selectedBlockId: null,
        expandedBlocks,
        editingBlockId: null,
      },
      past: [],
      future: [],
      strategyId: null,
      strategyName: metadata.name || previewTemplate.name,
      strategyDescription: previewTemplate.description,
      timeframe: metadata.timeframe || '1D',
      isDirty: false,
      loading: false,
      error: null,
    });
  }, [previewDialogOpen, previewTemplate]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      closePreviewDialog();
    }
  }, [closePreviewDialog]);

  useEffect(() => {
    if (!previewDialogOpen) return;

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [previewDialogOpen, handleKeyDown]);

  const handleOpenInEditor = useCallback(() => {
    if (!previewTemplate) return;

    closeAllStrategyDialogs();
    // Navigate with template ID - loadTemplate will fetch and set pendingTemplateId
    navigate(`/strategies/builder?template=${previewTemplate.id}`);
  }, [previewTemplate, closeAllStrategyDialogs, navigate]);

  if (!previewDialogOpen || !previewTemplate) return null;

  const difficultyColor = DIFFICULTY_COLORS[previewTemplate.difficulty] || '';
  const categoryColor = CATEGORY_COLORS[previewTemplate.category] || 'bg-gray-100 text-gray-700';

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center">
      {/* Backdrop - lighter since it sits on top of the template dialog's backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={closePreviewDialog} />

      <div className="relative bg-paper border-2 border-ink shadow-2xl w-[calc(100vw-120px)] h-[calc(100vh-100px)] max-w-[1100px] overflow-hidden mx-4 flex flex-col">
        <div className="flex items-center justify-between px-6 py-3 border-b-2 border-ink flex-shrink-0">
          <h2 className="text-[11px] font-mono font-bold uppercase tracking-wide text-ink/60">
            Template Preview
          </h2>
          <button
            onClick={closePreviewDialog}
            className="p-2 hover:bg-ink/5 transition-colors"
          >
            <X className="w-5 h-5 text-ink/60" />
          </button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          <div className="w-80 flex-shrink-0 border-r-2 border-ink p-6 overflow-y-auto">
            <h2 className="text-xl font-display uppercase tracking-tight text-ink mb-2">
              {previewTemplate.name}
            </h2>

            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {previewTemplate.description}
            </p>

            <div className="flex items-center gap-2 flex-wrap mb-6">
              <span className={`text-[10px] px-2 py-0.5 border border-ink font-mono font-bold uppercase tracking-wide ${difficultyColor}`}>
                {DIFFICULTY_LABELS[previewTemplate.difficulty] || previewTemplate.difficulty}
              </span>
              <span className={`text-[10px] px-2 py-0.5 border border-ink font-mono font-bold uppercase tracking-wide ${categoryColor}`}>
                {CATEGORY_LABELS[previewTemplate.category] || previewTemplate.category}
              </span>
            </div>

            {previewTemplate.tags.length > 0 && (
              <div className="mb-6">
                <span className="text-[11px] font-mono font-bold text-ink/50 uppercase tracking-wide">
                  Tags
                </span>
                <div className="flex flex-wrap gap-2 mt-2">
                  {previewTemplate.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 bg-bone border border-ink/20 font-mono uppercase tracking-wide text-ink/70"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="text-xs text-ink/60 bg-bone border-2 border-ink p-3">
              <p className="mb-1">
                <strong>Preview:</strong> The panel on the right shows this template&apos;s strategy logic.
              </p>
              <p>
                Open it in the editor to customize symbols, parameters, and rules, then run a backtest
                to see real performance.
              </p>
            </div>
          </div>

          <div className="flex-1 min-w-0 overflow-hidden">
            <StrategyBuilder readOnly />
          </div>
        </div>

        <div className="flex items-center justify-between px-6 py-4 border-t-2 border-ink bg-bone flex-shrink-0">
          <button
            onClick={closePreviewDialog}
            className="btn btn-ghost"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Templates
          </button>
          <button
            onClick={handleOpenInEditor}
            className="btn btn-primary btn-lg"
          >
            Open in Editor
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
