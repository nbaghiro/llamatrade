import { AlertCircle, ArrowLeft, Loader2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { StrategyBuilder } from '../../components/strategy-builder/StrategyBuilder';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

export default function StrategyEditorPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const templateId = searchParams.get('template');
  const artifactId = searchParams.get('artifact');

  // Track if we've already loaded to prevent double-execution in React 18 Strict Mode
  const hasLoadedRef = useRef(false);

  const { loadStrategy, loadTemplate, loadFromArtifact, createNew, loading, error, clearError, tree, isDirty } =
    useStrategyBuilderStore();

  useEffect(() => {
    // Prevent double-execution in React 18 Strict Mode
    if (hasLoadedRef.current) return;

    if (id) {
      // Edit existing strategy
      hasLoadedRef.current = true;
      loadStrategy(id);
    } else if (artifactId) {
      // Load from pending artifact (survives page refresh)
      hasLoadedRef.current = true;
      loadFromArtifact(artifactId);
    } else if (templateId) {
      // Create from template
      hasLoadedRef.current = true;
      loadTemplate(templateId);
    } else {
      // New strategy without template
      // Check if tree was already populated (e.g., from preview dialog)
      const currentTree = useStrategyBuilderStore.getState().tree;
      const hasContent = Object.keys(currentTree.blocks).length > 1;
      if (!hasContent) {
        hasLoadedRef.current = true;
        createNew();
      }
    }
  }, [id, artifactId, templateId, loadStrategy, loadFromArtifact, loadTemplate, createNew]);

  // Reset the ref when navigating to a new strategy
  useEffect(() => {
    return () => {
      hasLoadedRef.current = false;
    };
  }, [id, artifactId, templateId]);

  // Warn on browser refresh/close with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        // Modern browsers ignore custom messages, but returnValue must be set
        e.returnValue = '';
        return '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const handleBack = () => {
    navigate('/strategies');
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)]">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400">
            {id ? 'Loading strategy...' : artifactId ? 'Loading artifact...' : templateId ? 'Loading template...' : 'Initializing...'}
          </p>
        </div>
      </div>
    );
  }

  // Error state - only show full-page error for load failures
  // If tree has blocks beyond just root, load succeeded and save errors show inline
  const isLoadError = error && Object.keys(tree.blocks).length <= 1;
  if (isLoadError) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)]">
        <div className="text-center max-w-md">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Failed to load strategy
          </h2>
          <p className="text-gray-500 dark:text-gray-400 mb-4">{error}</p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={handleBack}
              className="flex items-center gap-2 px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Strategies
            </button>
            <button
              onClick={clearError}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-56px)]">
      <StrategyBuilder />
    </div>
  );
}
