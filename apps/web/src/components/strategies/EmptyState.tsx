import { LineChart, Plus } from 'lucide-react';

interface EmptyStateProps {
  onCreateFromTemplate: () => void;
  onCreateFromScratch: () => void;
}

export function EmptyState({ onCreateFromTemplate, onCreateFromScratch }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="p-4 bg-bone border-2 border-ink mb-4">
        <LineChart className="w-8 h-8 text-ink/40" />
      </div>
      <h3 className="text-lg font-display uppercase tracking-tight text-ink mb-2">No strategies yet</h3>
      <p className="text-gray-500 dark:text-gray-400 text-center max-w-md mb-6">
        Create your first strategy to get started. You can start from a template or build one from
        scratch.
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={onCreateFromTemplate}
          className="btn btn-primary"
        >
          <Plus className="w-4 h-4" />
          Create from Template
        </button>
        <button
          onClick={onCreateFromScratch}
          className="btn btn-secondary"
        >
          Start from Scratch
        </button>
      </div>
    </div>
  );
}
