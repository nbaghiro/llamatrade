import { TrendingUp } from 'lucide-react';

export default function TradingPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Live Trading</h1>
        <p className="text-slate-400 mt-1">Monitor and manage your live trading sessions</p>
      </div>

      <div className="card text-center py-12">
        <TrendingUp className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-white mb-2">No active sessions</h3>
        <p className="text-slate-400 mb-6">
          Start a trading session to begin live trading
        </p>
        <button className="btn btn-primary">Start Trading Session</button>
      </div>
    </div>
  );
}
