import { X, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { StrategyType as ProtoStrategyType, type Strategy } from '../../generated/proto/llamatrade/v1/strategy_pb';
import { strategyClient } from '../../services/grpc-client';

interface TemplateSelectorProps {
  onClose: () => void;
}

type StrategyType = 'trend_following' | 'mean_reversion' | 'momentum' | 'breakout' | 'custom';
type Difficulty = 'beginner' | 'intermediate' | 'advanced';

const TYPE_LABELS: Record<StrategyType, string> = {
  trend_following: 'Trend Following',
  mean_reversion: 'Mean Reversion',
  momentum: 'Momentum',
  breakout: 'Breakout',
  custom: 'Custom',
};

const DIFFICULTY_COLORS: Record<Difficulty, { bg: string; text: string }> = {
  beginner: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400' },
  intermediate: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
  },
  advanced: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400' },
};

// Extract template-like data from strategy
interface TemplateData {
  id: string;
  name: string;
  description: string;
  strategyType: StrategyType;
  difficulty: Difficulty;
  tags: string[];
}

// Convert proto type enum to UI string
function protoTypeToLocal(protoType: ProtoStrategyType): StrategyType {
  switch (protoType) {
    case ProtoStrategyType.DSL:
      return 'trend_following'; // Map DSL to a UI type
    case ProtoStrategyType.PYTHON:
      return 'custom';
    case ProtoStrategyType.TEMPLATE:
      return 'custom';
    default:
      return 'custom';
  }
}

function strategyToTemplate(strategy: Strategy): TemplateData {
  // Infer difficulty from strategy complexity or default to beginner
  const difficulty: Difficulty = 'beginner';

  return {
    id: strategy.id,
    name: strategy.name,
    description: strategy.description || '',
    strategyType: protoTypeToLocal(strategy.type),
    difficulty,
    tags: strategy.symbols.slice(0, 3),
  };
}

export function TemplateSelector({ onClose }: TemplateSelectorProps) {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<TemplateData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState<StrategyType | 'all'>('all');
  const [difficultyFilter, setDifficultyFilter] = useState<Difficulty | 'all'>('all');

  useEffect(() => {
    async function fetchTemplates() {
      try {
        setLoading(true);
        // List strategies that can serve as templates
        const response = await strategyClient.listStrategies({
          pagination: { page: 1, pageSize: 50 },
          types: [ProtoStrategyType.TEMPLATE], // Filter for template strategies
        });
        setTemplates(response.strategies.map(strategyToTemplate));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load templates');
      } finally {
        setLoading(false);
      }
    }
    fetchTemplates();
  }, []);

  const filteredTemplates = templates.filter((t) => {
    if (typeFilter !== 'all' && t.strategyType !== typeFilter) return false;
    if (difficultyFilter !== 'all' && t.difficulty !== difficultyFilter) return false;
    return true;
  });

  const handleSelect = (templateId: string) => {
    navigate(`/strategies/new?template=${templateId}`);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-3xl max-h-[80vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Choose a Template
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4 px-6 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600 dark:text-gray-400">Type:</label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as StrategyType | 'all')}
              className="px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md"
            >
              <option value="all">All</option>
              <option value="trend_following">Trend Following</option>
              <option value="mean_reversion">Mean Reversion</option>
              <option value="momentum">Momentum</option>
              <option value="breakout">Breakout</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600 dark:text-gray-400">Difficulty:</label>
            <select
              value={difficultyFilter}
              onChange={(e) => setDifficultyFilter(e.target.value as Difficulty | 'all')}
              className="px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md"
            >
              <option value="all">All</option>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto p-6" style={{ maxHeight: 'calc(80vh - 140px)' }}>
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          )}

          {error && (
            <div className="text-center py-12">
              <p className="text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {!loading && !error && filteredTemplates.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400">No templates match your filters</p>
            </div>
          )}

          {!loading && !error && filteredTemplates.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredTemplates.map((template) => (
                <button
                  key={template.id}
                  onClick={() => handleSelect(template.id)}
                  className="text-left p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 dark:hover:border-blue-500 hover:shadow-md transition-all"
                >
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-medium text-gray-900 dark:text-gray-100">{template.name}</h3>
                    <span
                      className={`px-2 py-0.5 text-xs font-medium rounded ${DIFFICULTY_COLORS[template.difficulty].bg} ${DIFFICULTY_COLORS[template.difficulty].text}`}
                    >
                      {template.difficulty}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
                    {template.description}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
                      {TYPE_LABELS[template.strategyType] || 'Custom'}
                    </span>
                    {template.tags.slice(0, 2).map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
