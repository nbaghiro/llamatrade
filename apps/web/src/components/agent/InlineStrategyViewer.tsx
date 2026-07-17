/** Renders a strategy visualization inline within chat messages, parsing DSL from the artifact preview. */

import type { PendingArtifact } from '@llamatrade/core/stores/agent';
import { AlertCircle, ChevronDown, ChevronRight, GitBranch, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import type { StrategyTree } from '@llamatrade/core/strategy/types';
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

  const previewData = useMemo<PreviewData | null>(() => {
    try {
      if (!artifact.previewJson) return null;
      return JSON.parse(artifact.previewJson) as PreviewData;
    } catch {
      return null;
    }
  }, [artifact.previewJson]);

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
    <div className="my-4 border-2 border-ink shadow overflow-hidden bg-paper">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 border-b-2 border-ink bg-bone flex items-center justify-between hover:bg-bone transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-ink/50" />
          ) : (
            <ChevronRight className="w-4 h-4 text-ink/50" />
          )}
          <GitBranch className="w-4 h-4 text-orange-500" />
          <span className="font-bold text-sm text-ink">
            {artifact.name || 'Strategy Preview'}
          </span>
        </div>
        <span className="text-xs font-mono uppercase tracking-wide bg-orange-500 text-ink border border-ink px-2 py-0.5">
          Strategy
        </span>
      </button>

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
    <div className="my-4 border-2 border-ink shadow overflow-hidden">
      <div className="px-3 py-2 bg-amber-50 flex items-center gap-2">
        <AlertCircle className="w-4 h-4 text-amber-600" />
        <span className="text-sm text-amber-700">
          {error}
        </span>
        {dslCode && (
          <button
            onClick={() => setShowCode(!showCode)}
            className="ml-auto text-xs font-mono uppercase tracking-wide text-amber-700 hover:underline flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" />
            {showCode ? 'Hide Code' : 'View Code'}
          </button>
        )}
      </div>

      {showCode && dslCode && (
        <pre className="p-3 text-xs overflow-auto bg-bone border-t-2 border-ink text-ink font-mono max-h-48">
          <code>{dslCode}</code>
        </pre>
      )}

      <div className="px-3 py-2 bg-paper border-t border-ink text-xs text-ink/60">
        <span className="font-bold">{artifact.name}</span>
        {artifact.description && (
          <span className="ml-2">&mdash; {artifact.description}</span>
        )}
      </div>
    </div>
  );
}
