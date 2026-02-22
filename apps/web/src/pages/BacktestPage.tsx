import { FlaskConical } from 'lucide-react';

export default function BacktestPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Backtesting</h1>
        <p className="text-slate-400 mt-1">Test your strategies against historical data</p>
      </div>

      <div className="card text-center py-12">
        <FlaskConical className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-white mb-2">No backtests yet</h3>
        <p className="text-slate-400 mb-6">
          Select a strategy and run a backtest to see results
        </p>
        <button className="btn btn-primary">Run Backtest</button>
      </div>
    </div>
  );
}
