import { ArrowRight, FileText, Layers, Plus, Sparkles, TrendingUp, Umbrella } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { STRATEGY_TEMPLATES, type StrategyTemplate } from '../../data/strategy-templates';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import type { BlockId } from '../../types/strategy-builder';
import { hasChildren } from '../../types/strategy-builder';

const CATEGORY_ICONS: Record<string, typeof TrendingUp> = {
  tactical: TrendingUp,
  factor: Sparkles,
  'all-weather': Umbrella,
  passive: Layers,
};

const CATEGORY_COLORS: Record<string, string> = {
  tactical: 'text-amber-500',
  factor: 'text-purple-500',
  'all-weather': 'text-blue-500',
  passive: 'text-green-500',
};

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  intermediate: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  advanced: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

interface TemplateCardProps {
  template: StrategyTemplate;
  onSelect: () => void;
}

function TemplateCard({ template, onSelect }: TemplateCardProps) {
  const CategoryIcon = CATEGORY_ICONS[template.category] || Layers;
  const categoryColor = CATEGORY_COLORS[template.category] || 'text-gray-500';
  const difficultyColor = DIFFICULTY_COLORS[template.difficulty] || '';

  return (
    <button
      onClick={onSelect}
      className="group text-left p-5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-primary-400 hover:shadow-lg dark:hover:border-primary-500 transition-all"
    >
      <div className="flex items-start gap-4">
        <div className={`p-2.5 rounded-lg bg-gray-100 dark:bg-gray-800 ${categoryColor}`}>
          <CategoryIcon className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-semibold text-gray-900 dark:text-gray-100">
              {template.name}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${difficultyColor}`}>
              {template.difficulty}
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-3 line-clamp-2">
            {template.description}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {template.blockTypes.map((type) => (
              <span
                key={type}
                className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
              >
                {type}
              </span>
            ))}
          </div>
        </div>
        <ArrowRight className="w-5 h-5 text-gray-300 dark:text-gray-600 group-hover:text-primary-500 group-hover:translate-x-1 transition-all" />
      </div>
    </button>
  );
}

export function NewStrategyPage() {
  const navigate = useNavigate();
  const { createNew } = useStrategyBuilderStore();

  const handleStartBlank = () => {
    createNew();
    navigate('/strategies/builder');
  };

  const handleSelectTemplate = (template: StrategyTemplate) => {
    // Generate fresh tree from template
    const tree = template.createTree();

    // Calculate expanded blocks
    const expandedBlocks = new Set<BlockId>();
    for (const block of Object.values(tree.blocks)) {
      if (hasChildren(block)) {
        expandedBlocks.add(block.id);
      }
    }

    // Update store directly
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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 py-12 px-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-3">
            Create New Strategy
          </h1>
          <p className="text-gray-500 dark:text-gray-400 max-w-lg mx-auto">
            Start from scratch or choose a template to get started quickly with a pre-built strategy structure.
          </p>
        </div>

        {/* Start Blank Card */}
        <button
          onClick={handleStartBlank}
          className="group w-full text-left p-6 mb-8 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-primary-400 dark:hover:border-primary-500 bg-white/50 dark:bg-gray-900/50 hover:bg-primary-50/50 dark:hover:bg-primary-900/20 transition-all"
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
          <div className="flex items-center gap-2 mb-4">
            <FileText className="w-5 h-5 text-gray-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Or start with a template
            </h2>
          </div>
          <div className="space-y-4">
            {STRATEGY_TEMPLATES.map((template) => (
              <TemplateCard
                key={template.id}
                template={template}
                onSelect={() => handleSelectTemplate(template)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
