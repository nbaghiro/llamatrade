/**
 * Tool call indicator component.
 *
 * Shows the current tool being executed by the agent.
 */

import { CheckCircle, Loader2, Wrench, XCircle } from 'lucide-react';

interface ToolCallIndicatorProps {
  toolName: string;
  status: 'running' | 'complete' | 'error';
  resultPreview?: string;
}

// Friendly names for tools
const TOOL_NAMES: Record<string, string> = {
  list_strategies: 'Listing strategies',
  get_strategy: 'Loading strategy',
  list_templates: 'Loading templates',
  get_portfolio_summary: 'Checking portfolio',
  get_portfolio_performance: 'Getting performance',
  get_positions: 'Loading positions',
  validate_dsl: 'Validating strategy',
  get_asset_info: 'Looking up assets',
  get_indicator_values: 'Getting indicators',
  get_backtest_results: 'Loading backtest',
  list_backtests: 'Listing backtests',
  run_backtest: 'Running backtest',
  create_pending_strategy: 'Creating strategy',
};

export function ToolCallIndicator({
  toolName,
  status,
  resultPreview,
}: ToolCallIndicatorProps) {
  const displayName = TOOL_NAMES[toolName] || toolName;

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm">
      {/* Icon */}
      <div className="flex-shrink-0">
        {status === 'running' && (
          <Loader2 className="w-4 h-4 text-purple-500 animate-spin" />
        )}
        {status === 'complete' && (
          <CheckCircle className="w-4 h-4 text-green-500" />
        )}
        {status === 'error' && (
          <XCircle className="w-4 h-4 text-red-500" />
        )}
      </div>

      {/* Tool icon */}
      <Wrench className="w-3 h-3 text-gray-400" />

      {/* Status text */}
      <span className="text-gray-600 dark:text-gray-300">{displayName}</span>

      {/* Result preview */}
      {resultPreview && status === 'complete' && (
        <span className="text-xs text-gray-400 truncate max-w-[200px]">
          {resultPreview}
        </span>
      )}
    </div>
  );
}
