import { Plus, Lightbulb } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function StrategiesPage() {
  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Strategies</h1>
          <p className="text-slate-400 mt-1">Create and manage your trading strategies</p>
        </div>
        <Link to="/strategies/new" className="btn btn-primary">
          <Plus className="w-5 h-5 mr-2" />
          New Strategy
        </Link>
      </div>

      {/* Empty state */}
      <div className="card text-center py-12">
        <Lightbulb className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-white mb-2">No strategies yet</h3>
        <p className="text-slate-400 mb-6">
          Create your first strategy or use one of our templates
        </p>
        <div className="flex gap-4 justify-center">
          <Link to="/strategies/new" className="btn btn-primary">
            Create Strategy
          </Link>
          <Link to="/strategies/new?template=ma_crossover" className="btn btn-secondary">
            Use Template
          </Link>
        </div>
      </div>
    </div>
  );
}
