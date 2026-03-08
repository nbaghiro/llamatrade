import { ArrowLeft, ArrowRight, Loader2, Plus, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { generateBenchmarkData, generateChartData } from '../../data/demo-strategies';
import {
  ALL_CATEGORIES,
  ALL_DIFFICULTIES,
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
  type StrategyTemplate,
  type TemplateCategory,
  type TemplateDifficulty,
} from '../../data/strategy-templates';
import { listTemplates } from '../../services/strategy';
import { fromDSLString } from '../../services/strategy-serializer';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import type { BlockId } from '../../types/strategy-builder';
import { hasChildren } from '../../types/strategy-builder';

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  intermediate: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  advanced: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

const CATEGORY_COLORS: Record<string, string> = {
  'buy-and-hold': 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  tactical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  factor: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  income: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  trend: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
  'mean-reversion': 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  alternatives: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
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
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
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
            {template.difficulty}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${categoryColor}`}>
            {template.category}
          </span>
        </div>
      </div>
    </button>
  );
}

export function NewStrategyPage() {
  const navigate = useNavigate();
  const { createNew } = useStrategyBuilderStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<TemplateCategory | 'all'>('all');
  const [selectedDifficulty, setSelectedDifficulty] = useState<TemplateDifficulty | 'all'>('all');

  // Template state - fetched from API
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch templates on mount
  useEffect(() => {
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
          strategy_type: t.strategyType,
          category: t.category as TemplateCategory,
          asset_class: t.assetClass as StrategyTemplate['asset_class'],
          config_sexpr: t.configSexpr,
          config_json: {},
          tags: [...t.tags],
          difficulty: t.difficulty as TemplateDifficulty,
        }));
        setTemplates(mappedTemplates);
      } catch {
        setError('Failed to load templates. Please try again.');
      } finally {
        setLoading(false);
      }
    }
    fetchTemplates();
  }, []);

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
    navigate('/strategies/builder');
  };

  const handleSelectTemplate = (template: StrategyTemplate) => {
    // Parse the S-expression DSL into a block tree
    const parseResult = fromDSLString(template.config_sexpr);

    if (!parseResult) {
      // Fallback: create empty strategy with just the name if DSL parsing fails
      createNew();
      useStrategyBuilderStore.setState({
        strategyName: template.name,
        strategyDescription: template.description,
      });
      navigate('/strategies/builder');
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
      strategyName: metadata.name || template.name,
      strategyDescription: template.description,
      strategyType: 'custom',
      timeframe: metadata.timeframe || '1D',
      isDirty: true,
      loading: false,
      error: null,
    });

    navigate('/strategies/builder');
  };

  return (
    <div className="min-h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950 bg-dotted-grid">
      <div className="px-12 py-8">
        {/* Header with Back Arrow */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <Link
              to="/strategies"
              className="p-2 -ml-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                New Strategy
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Start from scratch or choose a template
              </p>
            </div>
          </div>
        </div>

        {/* Search and Filter */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search templates..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
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

          {/* Vertical Separator */}
          <div className="w-px h-8 bg-gray-300 dark:bg-gray-600 mx-2" />

          {/* Difficulty Filter */}
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-500 self-center mr-1 uppercase tracking-wide">
              Level
            </span>
            {ALL_DIFFICULTIES.map((difficulty) => (
              <button
                key={difficulty}
                onClick={() => setSelectedDifficulty(selectedDifficulty === difficulty ? 'all' : difficulty)}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                  selectedDifficulty === difficulty
                    ? difficulty === 'beginner'
                      ? 'bg-green-600 text-white border-green-600'
                      : difficulty === 'intermediate'
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {/* Blank Strategy Ghost Card */}
          <button
            onClick={handleStartBlank}
            className="group relative h-full flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-primary-400 dark:hover:border-primary-500 bg-gradient-to-br from-gray-50/50 to-gray-100/50 dark:from-gray-900/50 dark:to-gray-800/30 hover:from-primary-50/60 hover:to-primary-100/40 dark:hover:from-primary-900/20 dark:hover:to-primary-800/10 transition-all overflow-hidden"
          >
            {/* Decorative background pattern */}
            <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]">
              <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <pattern id="grid-pattern" width="32" height="32" patternUnits="userSpaceOnUse">
                    <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" strokeWidth="1"/>
                  </pattern>
                </defs>
                <rect width="100%" height="100%" fill="url(#grid-pattern)" className="text-gray-900 dark:text-white" />
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
  );
}
