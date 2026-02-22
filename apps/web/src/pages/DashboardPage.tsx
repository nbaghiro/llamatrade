import { Activity, DollarSign, TrendingUp } from 'lucide-react';

const stats = [
  { label: 'Total Equity', value: '$100,000.00', change: '+2.5%', positive: true, icon: DollarSign },
  { label: 'Day P&L', value: '+$1,250.00', change: '+1.25%', positive: true, icon: TrendingUp },
  { label: 'Open Positions', value: '5', change: null, positive: null, icon: Activity },
  { label: 'Active Strategies', value: '3', change: null, positive: null, icon: Activity },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-slate-400 mt-1">Overview of your trading activity</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat) => (
          <div key={stat.label} className="card">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 text-sm">{stat.label}</span>
              <stat.icon className="w-5 h-5 text-slate-500" />
            </div>
            <div className="mt-2">
              <span className="text-2xl font-bold text-white">{stat.value}</span>
              {stat.change && (
                <span
                  className={`ml-2 text-sm ${
                    stat.positive ? 'text-success-500' : 'text-danger-500'
                  }`}
                >
                  {stat.change}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Recent activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Recent Trades</h2>
          <div className="text-slate-400 text-sm">No recent trades</div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Active Strategies</h2>
          <div className="text-slate-400 text-sm">No active strategies</div>
        </div>
      </div>
    </div>
  );
}
