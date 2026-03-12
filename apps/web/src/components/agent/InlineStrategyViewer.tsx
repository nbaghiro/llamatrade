/**
 * InlineStrategyViewer - Renders a strategy visualization inline within chat messages.
 *
 * Parses DSL from artifact preview and renders using the StrategyBuilder component
 * in a scoped store context.
 */

import { AlertCircle, ChevronDown, ChevronRight, GitBranch, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { fromDSLString } from '../../services/strategy-serializer';
import type { PendingArtifact } from '../../store/agent';
import type { StrategyTree } from '../../types/strategy-builder';
import { StrategyBuilder } from '../strategy-builder/StrategyBuilder';
import { StrategyBuilderStoreProvider } from '../strategy-builder/StrategyBuilderStoreProvider';

interface InlineStrategyViewerProps {
  /** The artifact containing the strategy DSL */
  artifact: PendingArtifact;
  /** Maximum height for the viewer (default 300px) */
  maxHeight?: number;
}

interface PreviewData {
  dsl_code?: string;
  name?: string;
  description?: string;
}

/**
 * Renders a view-only strategy visualization from an artifact.
 */
export function InlineStrategyViewer({
  artifact,
  maxHeight = 300,
}: InlineStrategyViewerProps) {
  const [tree, setTree] = useState<StrategyTree | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);

  // Parse the artifact preview JSON to extract DSL code
  const previewData = useMemo<PreviewData | null>(() => {
    try {
      if (!artifact.previewJson) return null;
      return JSON.parse(artifact.previewJson) as PreviewData;
    } catch {
      return null;
    }
  }, [artifact.previewJson]);

  // Parse DSL code into strategy tree
  useEffect(() => {
    setError(null);
    setTree(null);

    if (!previewData?.dsl_code) {
      setError('No strategy DSL found in artifact');
      return;
    }

    try {
      const parsed = fromDSLString(previewData.dsl_code);
      if (parsed) {
        setTree(parsed.tree);
      } else {
        setError('Failed to parse strategy DSL');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid strategy format');
    }
  }, [previewData]);

  // Show error fallback
  if (error || !tree) {
    return (
      <FallbackView
        artifact={artifact}
        dslCode={previewData?.dsl_code}
        error={error || 'Unable to render strategy preview'}
      />
    );
  }

  return (
    <div className="my-4 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-white dark:bg-gray-900">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 flex items-center justify-between hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500" />
          )}
          <GitBranch className="w-4 h-4 text-purple-500" />
          <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
            {artifact.name || 'Strategy Preview'}
          </span>
        </div>
        <span className="text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 px-2 py-0.5 rounded">
          Strategy
        </span>
      </button>

      {/* Strategy visualization */}
      {isExpanded && (
        <StrategyBuilderStoreProvider tree={tree} previewId={artifact.id}>
          <div style={{ maxHeight: maxHeight - 48 }} className="overflow-auto">
            <StrategyBuilder readOnly />
          </div>
        </StrategyBuilderStoreProvider>
      )}
    </div>
  );
}

/**
 * Fallback view when strategy cannot be rendered visually.
 * Shows the raw DSL code if available.
 */
function FallbackView({
  artifact,
  dslCode,
  error,
}: {
  artifact: PendingArtifact;
  dslCode: string | undefined;
  error: string;
}) {
  const [showCode, setShowCode] = useState(false);

  return (
    <div className="my-4 rounded-lg border border-amber-200 dark:border-amber-800 overflow-hidden">
      {/* Error header */}
      <div className="px-3 py-2 bg-amber-50 dark:bg-amber-900/20 flex items-center gap-2">
        <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
        <span className="text-sm text-amber-700 dark:text-amber-300">
          {error}
        </span>
        {dslCode && (
          <button
            onClick={() => setShowCode(!showCode)}
            className="ml-auto text-xs text-amber-600 dark:text-amber-400 hover:underline flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" />
            {showCode ? 'Hide Code' : 'View Code'}
          </button>
        )}
      </div>

      {/* Code preview */}
      {showCode && dslCode && (
        <pre className="p-3 text-xs overflow-auto bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300 font-mono max-h-48">
          <code>{dslCode}</code>
        </pre>
      )}

      {/* Artifact info */}
      <div className="px-3 py-2 bg-white dark:bg-gray-900 text-xs text-gray-500 dark:text-gray-400">
        <span className="font-medium">{artifact.name}</span>
        {artifact.description && (
          <span className="ml-2">&mdash; {artifact.description}</span>
        )}
      </div>
    </div>
  );
}
