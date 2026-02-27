import { LineChart, Plus } from 'lucide-react';

interface EmptyStateProps {
  onCreateFromTemplate: () => void;
  onCreateFromScratch: () => void;
}

export function EmptyState({ onCreateFromTemplate, onCreateFromScratch }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="p-4 bg-gray-100 dark:bg-gray-800 rounded-full mb-4">
        <LineChart className="w-8 h-8 text-gray-400 dark:text-gray-500" />
      </div>
      <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">No strategies yet</h3>
      <p className="text-gray-500 dark:text-gray-400 text-center max-w-md mb-6">
        Create your first strategy to get started. You can start from a template or build one from
        scratch.
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={onCreateFromTemplate}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create from Template
        </button>
        <button
          onClick={onCreateFromScratch}
          className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-lg transition-colors"
        >
          Start from Scratch
        </button>
      </div>
    </div>
  );
}
