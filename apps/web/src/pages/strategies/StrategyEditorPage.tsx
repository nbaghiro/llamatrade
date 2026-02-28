import { AlertCircle, ArrowLeft, Loader2 } from 'lucide-react';
import { useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { StrategyBuilder } from '../../components/strategy-builder/StrategyBuilder';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

export default function StrategyEditorPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const templateId = searchParams.get('template');

  const { loadStrategy, loadTemplate, loading, error, clearError } =
    useStrategyBuilderStore();

  useEffect(() => {
    if (id) {
      // Edit existing strategy
      loadStrategy(id);
    } else if (templateId) {
      // Create from template
      loadTemplate(templateId);
    }
    // Note: Don't call createNew() here - state is already set by NewStrategyPage
    // when navigating from the template picker
  }, [id, templateId, loadStrategy, loadTemplate]);

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
            {id ? 'Loading strategy...' : templateId ? 'Loading template...' : 'Initializing...'}
          </p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
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
