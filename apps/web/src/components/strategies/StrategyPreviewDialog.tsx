/**
 * Strategy Preview Dialog
 * Shows a preview of a strategy template before opening in the full editor.
 */

import { ArrowLeft, ArrowRight, X } from 'lucide-react';
import { useCallback, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { generateBenchmarkData, generateChartData } from '../../data/demo-strategies';
import {
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
  TemplateCategory,
  TemplateDifficulty,
} from '../../data/strategy-templates';
import { fromDSLString } from '../../services/strategy-serializer';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import { useUIStore } from '../../store/ui';
import type { BlockId } from '../../types/strategy-builder';
import { hasChildren } from '../../types/strategy-builder';
import { StrategyBuilder } from '../strategy-builder/StrategyBuilder';

const DIFFICULTY_COLORS: Record<TemplateDifficulty, string> = {
  [TemplateDifficulty.UNSPECIFIED]: 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400',
  [TemplateDifficulty.BEGINNER]: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400',
  [TemplateDifficulty.INTERMEDIATE]: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  [TemplateDifficulty.ADVANCED]: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

const CATEGORY_COLORS: Record<TemplateCategory, string> = {
  [TemplateCategory.UNSPECIFIED]: 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400',
  [TemplateCategory.BUY_AND_HOLD]: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  [TemplateCategory.TACTICAL]: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  [TemplateCategory.FACTOR]: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  [TemplateCategory.INCOME]: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  [TemplateCategory.TREND]: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
  [TemplateCategory.MEAN_REVERSION]: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  [TemplateCategory.ALTERNATIVES]: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
};

function MiniChart({
  data,
  benchmarkData,
  positive,
}: {
  data: number[];
  benchmarkData: number[];
  positive: boolean;
}) {
  const allValues = [...data, ...benchmarkData];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  const toPoints = (values: number[], width: number, height: number) =>
    values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = height - ((v - min) / range) * (height - 16);
        return `${x},${y}`;
      })
      .join(' ');

  const height = 120;
  const gradientId = `preview-gradient-${positive ? 'pos' : 'neg'}`;

  return (
    <svg viewBox="0 0 200 120" preserveAspectRatio="none" className="w-full h-[120px]">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0.2" />
          <stop offset="100%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${toPoints(data, 200, height)} 200,${height}`} fill={`url(#${gradientId})`} />
      <polyline
        points={toPoints(benchmarkData, 200, height)}
        fill="none"
        stroke="#9ca3af"
        strokeWidth="1"
        strokeDasharray="3,2"
        vectorEffect="non-scaling-stroke"
      />
      <polyline
        points={toPoints(data, 200, height)}
        fill="none"
        stroke={positive ? '#22c55e' : '#ef4444'}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default function StrategyPreviewDialog() {
  const navigate = useNavigate();
  const { previewDialogOpen, previewTemplate, closePreviewDialog, closeAllStrategyDialogs } = useUIStore();

  // Load the template into the strategy builder store when preview opens
  useEffect(() => {
    if (!previewDialogOpen || !previewTemplate) return;

    // Parse the S-expression DSL into a block tree
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

  // Handle ESC key to close preview dialog
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

  // Generate mock performance data
  const templateIndex = useMemo(() => {
    if (!previewTemplate) return 0;
    // Use template ID hash for consistent data
    let hash = 0;
    for (let i = 0; i < previewTemplate.id.length; i++) {
      hash = ((hash << 5) - hash) + previewTemplate.id.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash) % 100;
  }, [previewTemplate]);

  const chartData = useMemo(() => generateChartData(templateIndex * 7 + 3), [templateIndex]);
  const benchmarkData = useMemo(() => generateBenchmarkData(templateIndex * 5 + 2), [templateIndex]);
  const isPositive = chartData[chartData.length - 1] > chartData[0];

  const returnPct = ((chartData[chartData.length - 1] / chartData[0] - 1) * 100).toFixed(1);
  const sharpe = (1.2 + (templateIndex % 5) * 0.15).toFixed(2);
  const maxDD = (-(3 + (templateIndex % 7) * 1.5)).toFixed(1);

  if (!previewDialogOpen || !previewTemplate) return null;

  const difficultyColor = DIFFICULTY_COLORS[previewTemplate.difficulty] || '';
  const categoryColor = CATEGORY_COLORS[previewTemplate.category] || 'bg-gray-100 text-gray-700';

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center">
      {/* Backdrop - lighter since it sits on top of the template dialog's backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={closePreviewDialog} />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-[calc(100vw-120px)] h-[calc(100vh-100px)] max-w-[1100px] overflow-hidden mx-4 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Template Preview
          </h2>
          <button
            onClick={closePreviewDialog}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content - Two panel layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel - Template Info */}
          <div className="w-80 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 p-6 overflow-y-auto">
            {/* Template Name */}
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {previewTemplate.name}
            </h2>

            {/* Description */}
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {previewTemplate.description}
            </p>

            {/* Badges */}
            <div className="flex items-center gap-2 flex-wrap mb-6">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${difficultyColor}`}>
                {DIFFICULTY_LABELS[previewTemplate.difficulty] || previewTemplate.difficulty}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${categoryColor}`}>
                {CATEGORY_LABELS[previewTemplate.category] || previewTemplate.category}
              </span>
            </div>

            {/* Mini Chart */}
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 mb-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Simulated Performance
                </span>
              </div>
              <MiniChart data={chartData} benchmarkData={benchmarkData} positive={isPositive} />
              <div className="flex items-center justify-center gap-4 mt-3 text-xs text-gray-400 dark:text-gray-500">
                <span className="flex items-center gap-1">
                  <span className={`w-3 h-0.5 ${isPositive ? 'bg-green-500' : 'bg-red-500'}`} />
                  Strategy
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-gray-400 opacity-50" style={{ borderTop: '1px dashed' }} />
                  Benchmark
                </span>
              </div>
            </div>

            {/* Performance Stats */}
            <div className="grid grid-cols-3 gap-3 mb-6">
              <div className="text-center p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <div className={`text-lg font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                  {isPositive ? '+' : ''}{returnPct}%
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Return</div>
              </div>
              <div className="text-center p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <div className="text-lg font-bold text-gray-700 dark:text-gray-300">{sharpe}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Sharpe</div>
              </div>
              <div className="text-center p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <div className="text-lg font-bold text-red-500">{maxDD}%</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Max DD</div>
              </div>
            </div>

            {/* Info Note */}
            <div className="text-xs text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
              <p className="mb-1">
                <strong>Note:</strong> Performance shown is simulated and for demonstration purposes only.
              </p>
              <p>
                Past performance does not guarantee future results.
              </p>
            </div>
          </div>

          {/* Right Panel - Strategy Builder Preview */}
          <div className="flex-1 min-w-0 overflow-hidden">
            <StrategyBuilder readOnly />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
          <button
            onClick={closePreviewDialog}
            className="flex items-center gap-2 px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Templates
          </button>
          <button
            onClick={handleOpenInEditor}
            className="flex items-center gap-2 px-6 py-2.5 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
          >
            Open in Editor
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
