import { Save, Play, ArrowLeft } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

export default function StrategyEditorPage() {
  const [name, setName] = useState('');
  const [symbols, setSymbols] = useState('AAPL');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/strategies" className="btn btn-ghost p-2">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white">Strategy Editor</h1>
            <p className="text-slate-400">Build your trading strategy</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button className="btn btn-secondary">
            <Play className="w-5 h-5 mr-2" />
            Backtest
          </button>
          <button className="btn btn-primary">
            <Save className="w-5 h-5 mr-2" />
            Save
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Strategy config */}
        <div className="card space-y-4">
          <h2 className="text-lg font-semibold text-white">Configuration</h2>

          <div>
            <label className="label">Strategy Name</label>
            <input
              type="text"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Strategy"
            />
          </div>

          <div>
            <label className="label">Symbols</label>
            <input
              type="text"
              className="input"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="AAPL, GOOGL"
            />
          </div>

          <div>
            <label className="label">Timeframe</label>
            <select className="input">
              <option value="1D">Daily</option>
              <option value="1H">Hourly</option>
              <option value="15m">15 Minutes</option>
              <option value="5m">5 Minutes</option>
            </select>
          </div>
        </div>

        {/* Visual builder canvas */}
        <div className="lg:col-span-2 card min-h-[500px]">
          <h2 className="text-lg font-semibold text-white mb-4">Strategy Builder</h2>
          <div className="h-full flex items-center justify-center text-slate-500 border-2 border-dashed border-slate-700 rounded-lg">
            <p>Visual strategy builder canvas</p>
          </div>
        </div>
      </div>
    </div>
  );
}
