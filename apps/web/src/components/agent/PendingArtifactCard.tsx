/**
 * Pending artifact card component.
 *
 * Shows a preview of generated strategies with commit/dismiss actions.
 */

import { Check, CheckCircle2, ChevronDown, ChevronUp, ExternalLink, FileCode2, FlaskConical, Save, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { ArtifactType, PendingArtifact } from '../../store/agent';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

/**
 * Format DSL code with proper indentation for readability.
 */
function formatDSL(code: string): string {
  const result: string[] = [];
  let indent = 0;
  let i = 0;
  let lineStart = true;

  const addIndent = () => '  '.repeat(indent);

  while (i < code.length) {
    const char = code[i];

    if (char === '(') {
      // Check what follows the opening paren
      const rest = code.slice(i + 1).trimStart();
      const keyword = rest.match(/^(strategy|weight|group|if|else|filter|asset|and|or)\b/)?.[1];

      if (keyword === 'strategy') {
        // Strategy is the root - start on new line if not at start
        if (result.length > 0) {
          result.push('\n' + addIndent());
        } else if (lineStart) {
          result.push(addIndent());
        }
        result.push('(');
        indent++;
        lineStart = false;
      } else if (keyword && keyword !== 'asset') {
        // Major blocks get their own line
        result.push('\n' + addIndent() + '(');
        indent++;
        lineStart = false;
      } else if (keyword === 'asset') {
        // Assets on their own line
        result.push('\n' + addIndent() + '(');
        lineStart = false;
      } else {
        result.push('(');
        lineStart = false;
      }
    } else if (char === ')') {
      // Check if this closes a major block
      const nextChar = code[i + 1];
      if (nextChar === ')' || !nextChar) {
        result.push(')');
        indent = Math.max(0, indent - 1);
      } else {
        result.push(')');
        if (indent > 0) indent--;
      }
      lineStart = false;
    } else if (char === ' ' || char === '\t' || char === '\n') {
      // Collapse whitespace
      if (!lineStart && result[result.length - 1] !== ' ' && result[result.length - 1] !== '\n') {
        result.push(' ');
      }
      // Skip consecutive whitespace
      while (i + 1 < code.length && /\s/.test(code[i + 1])) {
        i++;
      }
    } else {
      result.push(char);
      lineStart = false;
    }
    i++;
  }

  return result.join('').trim();
}

interface PendingArtifactCardProps {
  artifact: PendingArtifact;
  onDismiss?: (artifactId: string) => void;
}

export function PendingArtifactCard({
  artifact,
  onDismiss,
}: PendingArtifactCardProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [hasBeenOpened, setHasBeenOpened] = useState(false);

  // Check if we're on the strategy builder page
  const isOnBuilderPage = location.pathname.includes('/strategies/builder') ||
    (location.pathname.startsWith('/strategies/') && location.pathname !== '/strategies');

  // Get builder store actions for when on builder page
  const { saveStrategy, isDirty, saving, strategyId } = useStrategyBuilderStore();

  // Parse the preview JSON
  let preview: StrategyPreview | null = null;
  try {
    preview = JSON.parse(artifact.previewJson) as StrategyPreview;
  } catch {
    // Invalid JSON
  }

  // Format DSL code with proper indentation
  const formattedDSL = useMemo(() => {
    if (!preview?.dsl_code) return '';
    return formatDSL(preview.dsl_code);
  }, [preview?.dsl_code]);

  const handleOpenInBuilder = () => {
    if (!preview?.dsl_code) return;

    // Store the DSL in sessionStorage for the builder to pick up
    sessionStorage.setItem('copilot-strategy', JSON.stringify({
      dslCode: preview.dsl_code,
      name: artifact.name,
      description: artifact.description || preview.description,
    }));

    setHasBeenOpened(true);

    // Navigate to builder
    navigate('/strategies/builder?from=copilot');
  };

  const handleSaveStrategy = async () => {
    await saveStrategy();
  };

  const handleRunBacktest = () => {
    // Navigate to backtest page
    if (strategyId) {
      navigate(`/backtest?strategy=${strategyId}`);
    } else {
      navigate('/backtest');
    }
  };

  const isStrategy = artifact.artifactType === ArtifactType.STRATEGY;
  const isCommitted = artifact.isCommitted;
  const showOpenedState = hasBeenOpened || isOnBuilderPage;

  return (
    <div className={`rounded-lg border overflow-hidden ${
      showOpenedState
        ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/10'
        : 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/10'
    }`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-3 py-2 border-b ${
        showOpenedState
          ? 'border-green-200 dark:border-green-800'
          : 'border-blue-200 dark:border-blue-800'
      }`}>
        <div className="flex items-center gap-2">
          <FileCode2 className={`w-4 h-4 ${showOpenedState ? 'text-green-500' : 'text-blue-500'}`} />
          <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
            {artifact.name}
          </span>
          {isStrategy && !showOpenedState && (
            <span className="px-1.5 py-0.5 text-[10px] uppercase tracking-wide font-medium rounded bg-blue-200 dark:bg-blue-800 text-blue-700 dark:text-blue-300">
              Strategy
            </span>
          )}
          {showOpenedState && (
            <span className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] uppercase tracking-wide font-medium rounded bg-green-200 dark:bg-green-800 text-green-700 dark:text-green-300">
              <CheckCircle2 className="w-3 h-3" />
              In Builder
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {!isCommitted && !showOpenedState && (
            <>
              <button
                onClick={handleOpenInBuilder}
                disabled={!preview?.dsl_code}
                className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded text-white disabled:opacity-50 transition-all"
                style={{
                  background: 'linear-gradient(90deg, #2563EB 0%, #0891B2 100%)',
                }}
              >
                <ExternalLink className="w-3 h-3" />
                Open
              </button>
              {onDismiss && (
                <button
                  onClick={() => onDismiss(artifact.id)}
                  className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                  title="Dismiss"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </>
          )}
          {!isCommitted && showOpenedState && (
            <>
              <button
                onClick={handleSaveStrategy}
                disabled={!isDirty || saving}
                className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 transition-all"
              >
                <Save className="w-3 h-3" />
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={handleRunBacktest}
                className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded bg-purple-600 hover:bg-purple-700 text-white transition-all"
              >
                <FlaskConical className="w-3 h-3" />
                Backtest
              </button>
              {onDismiss && (
                <button
                  onClick={() => onDismiss(artifact.id)}
                  className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                  title="Dismiss"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </>
          )}
          {isCommitted && (
            <a
              href={`/strategies/${artifact.committedResourceId}`}
              className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
            >
              <Check className="w-3 h-3" />
              Saved
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            {isExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Collapsed preview - show formatted code with more lines */}
      {!isExpanded && formattedDSL && (
        <pre className="px-3 py-2 text-xs text-gray-600 dark:text-gray-400 font-mono whitespace-pre-wrap max-h-24 overflow-hidden">
          {formattedDSL}
        </pre>
      )}

      {/* Expanded preview */}
      {isExpanded && preview && (
        <div className="p-3 space-y-3">
          {artifact.description && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {artifact.description}
            </p>
          )}

          {formattedDSL && (
            <div>
              <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                DSL Code
              </div>
              <pre className="p-3 rounded bg-gray-100 dark:bg-gray-800 text-xs font-mono text-gray-800 dark:text-gray-200 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
                {formattedDSL}
              </pre>
            </div>
          )}

          {preview.symbols && preview.symbols.length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Symbols
              </div>
              <div className="flex flex-wrap gap-1">
                {preview.symbols.map((symbol) => (
                  <span
                    key={symbol}
                    className="px-1.5 py-0.5 text-xs font-mono rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  >
                    {symbol}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface StrategyPreview {
  name?: string;
  description?: string;
  dsl_code?: string;
  symbols?: string[];
  timeframe?: string;
}
