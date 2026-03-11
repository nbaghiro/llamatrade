/**
 * New Strategy Dialog
 * Modal for creating a new strategy - select from templates or start from scratch.
 */

import { ArrowRight, Loader2, Plus, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { generateBenchmarkData, generateChartData } from '../../data/demo-strategies';
import {
  ALL_CATEGORIES,
  ALL_DIFFICULTIES,
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
  TemplateCategory,
  TemplateDifficulty,
  type StrategyTemplate,
} from '../../data/strategy-templates';
import { listTemplates } from '../../services/strategy';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import { useUIStore } from '../../store/ui';

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

interface NewStrategyDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

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
        const y = height - ((v - min) / range) * (height - 8);
        return `${x},${y}`;
      })
      .join(' ');

  const height = 70;
  const gradientId = `gradient-${positive ? 'pos' : 'neg'}-${Math.random().toString(36).slice(2)}`;

  return (
    <svg viewBox="0 0 100 70" preserveAspectRatio="none" className="w-full h-[70px]">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0.15" />
          <stop offset="100%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${toPoints(data, 100, height)} 100,${height}`} fill={`url(#${gradientId})`} />
      <polyline
        points={toPoints(benchmarkData, 100, height)}
        fill="none"
        stroke="#9ca3af"
        strokeWidth="0.8"
        strokeDasharray="2,1.5"
        vectorEffect="non-scaling-stroke"
      />
      <polyline
        points={toPoints(data, 100, height)}
        fill="none"
        stroke={positive ? '#22c55e' : '#ef4444'}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

interface TemplateCardProps {
  template: StrategyTemplate;
  index: number;
  onSelect: () => void;
}

function TemplateCard({ template, index, onSelect }: TemplateCardProps) {
  const difficultyColor = DIFFICULTY_COLORS[template.difficulty] || '';
  const categoryColor = CATEGORY_COLORS[template.category] || 'bg-gray-100 text-gray-700';

  // Generate consistent chart data based on template index
  const chartData = useMemo(() => generateChartData(index * 7 + 3), [index]);
  const benchmarkData = useMemo(() => generateBenchmarkData(index * 5 + 2), [index]);
  const isPositive = chartData[chartData.length - 1] > chartData[0];

  // Mock performance metrics
  const returnPct = ((chartData[chartData.length - 1] / chartData[0] - 1) * 100).toFixed(1);
  const sharpe = (1.2 + (index % 5) * 0.15).toFixed(2);
  const maxDD = (-(3 + (index % 7) * 1.5)).toFixed(1);

  return (
    <button
      onClick={onSelect}
      className="group h-full text-left rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-primary-400 dark:hover:border-primary-500 hover:shadow-lg transition-all overflow-hidden flex flex-col"
    >
      {/* Chart Section - Full Width */}
      <div className="bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
        <MiniChart data={chartData} benchmarkData={benchmarkData} positive={isPositive} />
      </div>

      {/* Content Section */}
      <div className="p-4 flex-1 flex flex-col">
        {/* Stats Row */}
        <div className="flex items-center gap-4 mb-3 text-sm">
          <div>
            <span className={`font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
              {isPositive ? '+' : ''}{returnPct}%
            </span>
            <span className="text-gray-400 dark:text-gray-500 ml-1 text-xs">Return</span>
          </div>
          <div>
            <span className="font-semibold text-gray-700 dark:text-gray-300">{sharpe}</span>
            <span className="text-gray-400 dark:text-gray-500 ml-1 text-xs">Sharpe</span>
          </div>
          <div>
            <span className="font-semibold text-red-500">{maxDD}%</span>
            <span className="text-gray-400 dark:text-gray-500 ml-1 text-xs">Max DD</span>
          </div>
        </div>

        {/* Title */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors truncate">
            {template.name}
          </h3>
          <ArrowRight className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-primary-500 group-hover:translate-x-1 transition-all flex-shrink-0 mt-1" />
        </div>

        {/* Description */}
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3 line-clamp-2">
          {template.description}
        </p>

        {/* Badges */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${difficultyColor}`}>
            {DIFFICULTY_LABELS[template.difficulty] || template.difficulty}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${categoryColor}`}>
            {CATEGORY_LABELS[template.category] || template.category}
          </span>
        </div>
      </div>
    </button>
  );
}

export default function NewStrategyDialog({ isOpen, onClose }: NewStrategyDialogProps) {
  const navigate = useNavigate();
  const { createNew } = useStrategyBuilderStore();
  const { openPreviewDialog, previewDialogOpen } = useUIStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<TemplateCategory | 'all'>('all');
  const [selectedDifficulty, setSelectedDifficulty] = useState<TemplateDifficulty | 'all'>('all');

  // Template state - fetched from API
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch templates when dialog opens
  useEffect(() => {
    if (!isOpen) return;

    async function fetchTemplates() {
      try {
        setLoading(true);
        setError(null);
        const response = await listTemplates();
        // Map proto response to StrategyTemplate type
        const mappedTemplates: StrategyTemplate[] = response.templates.map((t) => ({
          id: t.id,
          name: t.name,
          description: t.description,
          category: t.category,
          asset_class: t.assetClass,
          config_sexpr: t.configSexpr,
          config_json: {},
          tags: [...t.tags],
          difficulty: t.difficulty,
        }));
        setTemplates(mappedTemplates);
      } catch {
        setError('Failed to load templates. Please try again.');
      } finally {
        setLoading(false);
      }
    }
    fetchTemplates();
  }, [isOpen]);

  // Handle ESC key to close dialog (only if preview is not open)
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e: KeyboardEvent) {
      // Don't close if preview dialog is open - let preview handle ESC
      if (e.key === 'Escape' && !previewDialogOpen) {
        onClose();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, previewDialogOpen]);

  const filteredTemplates = useMemo(() => {
    return templates.filter((template) => {
      const matchesSearch =
        searchQuery === '' ||
        template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        template.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === 'all' || template.category === selectedCategory;
      const matchesDifficulty = selectedDifficulty === 'all' || template.difficulty === selectedDifficulty;
      return matchesSearch && matchesCategory && matchesDifficulty;
    });
  }, [templates, searchQuery, selectedCategory, selectedDifficulty]);

  const handleStartBlank = () => {
    createNew();
    onClose();
    navigate('/strategies/builder');
  };

  const handleSelectTemplate = (template: StrategyTemplate) => {
    // Open preview dialog instead of navigating directly
    openPreviewDialog(template);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal - large width for 4-col grid */}
      <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-7xl max-h-[85vh] overflow-hidden mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              New Strategy
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Start from scratch or choose a template
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Search and Filter */}
        <div className="px-6 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 space-y-3">
          {/* Row 1: Search, Categories, Count */}
          <div className="flex items-center gap-3">
            <div className="relative w-64 flex-shrink-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search templates..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                autoFocus
              />
            </div>

            {/* Category Filter */}
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setSelectedCategory('all')}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                  selectedCategory === 'all'
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-primary-400'
                }`}
              >
                All
              </button>
              {ALL_CATEGORIES.map((category) => (
                <button
                  key={category}
                  onClick={() => setSelectedCategory(category)}
                  className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                    selectedCategory === category
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-primary-400'
                  }`}
                >
                  {CATEGORY_LABELS[category]}
                </button>
              ))}
            </div>

            {/* Template Count - pinned right */}
            <div className="ml-auto flex-shrink-0">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {loading ? (
                  <span className="text-gray-400">...</span>
                ) : (
                  <>
                    <span className="font-semibold text-gray-700 dark:text-gray-300">{filteredTemplates.length}</span>
                    {' '}{filteredTemplates.length === 1 ? 'template' : 'templates'}
                  </>
                )}
              </span>
            </div>
          </div>

          {/* Row 2: Difficulty Filter */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-500 mr-1 uppercase tracking-wide">
              Level
            </span>
            {ALL_DIFFICULTIES.map((difficulty) => (
              <button
                key={difficulty}
                onClick={() => setSelectedDifficulty(selectedDifficulty === difficulty ? 'all' : difficulty)}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                  selectedDifficulty === difficulty
                    ? difficulty === TemplateDifficulty.BEGINNER
                      ? 'bg-sky-600 text-white border-sky-600'
                      : difficulty === TemplateDifficulty.INTERMEDIATE
                        ? 'bg-amber-500 text-white border-amber-500'
                        : 'bg-red-600 text-white border-red-600'
                    : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-primary-400'
                }`}
              >
                {DIFFICULTY_LABELS[difficulty]}
              </button>
            ))}
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="overflow-y-auto p-6 pb-16" style={{ maxHeight: 'calc(85vh - 160px)' }}>
          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
              <span className="ml-3 text-gray-500 dark:text-gray-400">Loading templates...</span>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="text-center py-12">
              <p className="text-red-500 dark:text-red-400">{error}</p>
              <button
                onClick={() => window.location.reload()}
                className="mt-4 px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                Retry
              </button>
            </div>
          )}

          {/* Template Grid with Blank Card as first item */}
          {!loading && !error && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {/* Blank Strategy Ghost Card */}
              <button
                onClick={handleStartBlank}
                className="group relative h-full min-h-[200px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-primary-400 dark:hover:border-primary-500 bg-gradient-to-br from-gray-50/50 to-gray-100/50 dark:from-gray-900/50 dark:to-gray-800/30 hover:from-primary-50/60 hover:to-primary-100/40 dark:hover:from-primary-900/20 dark:hover:to-primary-800/10 transition-all overflow-hidden"
              >
                {/* Decorative background pattern */}
                <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]">
                  <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                      <pattern id="dialog-grid-pattern" width="32" height="32" patternUnits="userSpaceOnUse">
                        <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" strokeWidth="1"/>
                      </pattern>
                    </defs>
                    <rect width="100%" height="100%" fill="url(#dialog-grid-pattern)" className="text-gray-900 dark:text-white" />
                  </svg>
                </div>

                {/* Decorative corner accents */}
                <div className="absolute top-3 left-3 w-8 h-8 border-l-2 border-t-2 border-gray-300 dark:border-gray-600 rounded-tl-lg opacity-50 group-hover:border-primary-400 dark:group-hover:border-primary-500 transition-colors" />
                <div className="absolute bottom-3 right-3 w-8 h-8 border-r-2 border-b-2 border-gray-300 dark:border-gray-600 rounded-br-lg opacity-50 group-hover:border-primary-400 dark:group-hover:border-primary-500 transition-colors" />

                {/* Content */}
                <div className="relative z-10 flex flex-col items-center">
                  <div className="p-4 rounded-2xl bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500 group-hover:border-primary-300 dark:group-hover:border-primary-600 group-hover:text-primary-500 dark:group-hover:text-primary-400 group-hover:shadow-md transition-all mb-4">
                    <Plus className="w-8 h-8" strokeWidth={1.5} />
                  </div>
                  <span className="font-semibold text-gray-700 dark:text-gray-300 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                    Start from Scratch
                  </span>
                  <p className="text-sm text-gray-400 dark:text-gray-500 mt-1 text-center px-4">
                    Design your own allocation
                  </p>
                </div>
              </button>

              {/* Template Cards */}
              {filteredTemplates.map((template, index) => (
                <TemplateCard
                  key={template.id}
                  template={template}
                  index={index}
                  onSelect={() => handleSelectTemplate(template)}
                />
              ))}
            </div>
          )}

          {/* Empty state when no templates match */}
          {!loading && !error && filteredTemplates.length === 0 && searchQuery && (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400">No templates match your search.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
