
export default function PortfolioPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Portfolio</h1>
        <p className="text-slate-400 mt-1">Track your positions and performance</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card">
          <p className="text-slate-400 text-sm">Total Equity</p>
          <p className="text-2xl font-bold text-white mt-1">$100,000.00</p>
        </div>
        <div className="card">
          <p className="text-slate-400 text-sm">Available Cash</p>
          <p className="text-2xl font-bold text-white mt-1">$100,000.00</p>
        </div>
        <div className="card">
          <p className="text-slate-400 text-sm">Total P&L</p>
          <p className="text-2xl font-bold text-success-500 mt-1">$0.00 (0%)</p>
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Positions</h2>
        <div className="text-slate-400 text-sm">No open positions</div>
      </div>
    </div>
  );
}
