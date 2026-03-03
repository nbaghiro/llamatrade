import { ArrowRight, Plus, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { generateBenchmarkData, generateChartData } from '../../data/demo-strategies';
import {
  STRATEGY_TEMPLATES,
  type StrategyTemplate,
  type TemplateCategory,
} from '../../data/strategy-templates';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import type { BlockId } from '../../types/strategy-builder';
import { hasChildren } from '../../types/strategy-builder';

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  intermediate: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  advanced: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

const CATEGORY_COLORS: Record<string, string> = {
  passive: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  income: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  growth: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
  'all-weather': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  tactical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  factor: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
};

const CATEGORY_LABELS: Record<TemplateCategory, string> = {
  passive: 'Passive',
  income: 'Income',
  growth: 'Growth',
  'all-weather': 'All-Weather',
  tactical: 'Tactical',
  factor: 'Factor',
};

const ALL_CATEGORIES: TemplateCategory[] = ['passive', 'income', 'growth', 'all-weather', 'tactical', 'factor'];

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
      className="group text-left rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-primary-400 dark:hover:border-primary-500 hover:shadow-lg transition-all overflow-hidden"
    >
      {/* Chart Section - Full Width */}
      <div className="bg-gray-50 dark:bg-gray-800/50">
        <MiniChart data={chartData} benchmarkData={benchmarkData} positive={isPositive} />
      </div>

      {/* Content Section */}
      <div className="p-4">
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

  const filteredTemplates = useMemo(() => {
    return STRATEGY_TEMPLATES.filter((template) => {
      const matchesSearch =
        searchQuery === '' ||
        template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        template.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === 'all' || template.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [searchQuery, selectedCategory]);

  const handleStartBlank = () => {
    createNew();
    navigate('/strategies/builder');
  };

  const handleSelectTemplate = (template: StrategyTemplate) => {
    const tree = template.createTree();

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
      strategyName: template.name,
      strategyDescription: template.description,
      strategyType: 'custom',
      timeframe: '1D',
      isDirty: true,
      loading: false,
      error: null,
    });

    navigate('/strategies/builder');
  };

  return (
    <div className="min-h-[calc(100vh-56px)] bg-gray-50 dark:bg-gray-950 bg-dotted-grid py-10 px-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Create New Strategy
          </h1>
          <p className="text-gray-500 dark:text-gray-400">
            Start from scratch or choose a template with pre-built allocation structures
          </p>
        </div>

        {/* Start Blank Card */}
        <button
          onClick={handleStartBlank}
          className="group w-full text-left p-5 mb-8 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-primary-400 dark:hover:border-primary-500 bg-white/50 dark:bg-gray-900/50 hover:bg-primary-50/50 dark:hover:bg-primary-900/20 transition-all"
        >
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400">
              <Plus className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <span className="font-semibold text-lg text-gray-900 dark:text-gray-100">
                Start from Scratch
              </span>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                Create a blank strategy and build your own allocation structure
              </p>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-300 dark:text-gray-600 group-hover:text-primary-500 group-hover:translate-x-1 transition-all" />
          </div>
        </button>

        {/* Templates Section */}
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
            Or start with a template
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            Pre-built strategies with sample backtesting performance
          </p>

          {/* Search and Filter */}
          <div className="flex flex-col sm:flex-row gap-3">
            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search templates..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-primary-400 focus:ring-1 focus:ring-primary-400 outline-none"
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
          </div>
        </div>

        {/* Template Grid */}
        {filteredTemplates.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">No templates match your search.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
      </div>
    </div>
  );
}
