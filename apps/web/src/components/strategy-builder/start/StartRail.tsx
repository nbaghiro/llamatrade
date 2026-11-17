import { useEffect, useState } from 'react';

import { isValidSymbol, normaliseSymbol, REBALANCE_OPTIONS } from '../../../lib/outline';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { KeyValue, RailPanel } from '../rail/RailPanel';

/** start2 A: the draft's settings while it has no rules yet, and what it needs. */
export function StartRail() {
  const { strategyName, setStrategyName, timeframe, setTimeframe, benchmark, setBenchmark } =
    useStrategyBuilderStoreWithContext();
  const [bench, setBench] = useState(benchmark);
  const [benchError, setBenchError] = useState<string | null>(null);
  useEffect(() => setBench(benchmark), [benchmark]);

  const commitBench = () => {
    const v = bench.trim();
    if (v === '') {
      setBenchError(null);
      setBenchmark('');
      return;
    }
    if (!isValidSymbol(v)) {
      setBenchError('Enter a ticker, for example SPY.');
      return;
    }
    setBenchError(null);
    setBenchmark(normaliseSymbol(v));
  };

  return (
    <div className="grid gap-4">
      <RailPanel title="Settings">
        <label className="grid gap-1.5">
          <span className="text-[12px] text-fg-2">Name</span>
          <input
            className="input"
            value={strategyName}
            onChange={(e) => setStrategyName(e.target.value)}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="text-[12px] text-fg-2">Rebalance</span>
          <select
            className="input"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          >
            {REBALANCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label.charAt(0).toUpperCase() + o.label.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5">
          <span className="text-[12px] text-fg-2">Benchmark</span>
          <input
            className={`input font-mono ${benchError ? 'input-error' : ''}`}
            value={bench}
            placeholder="None"
            onChange={(e) => setBench(e.target.value.toUpperCase())}
            onBlur={commitBench}
          />
          {benchError && <span className="text-[12px] text-risk">{benchError}</span>}
        </label>
      </RailPanel>
      <RailPanel title="What it needs">
        <div>
          <KeyValue k="Symbols" v={<span className="num">None yet</span>} />
          <KeyValue k="History before first rebalance" v={<span className="num">None</span>} />
          <KeyValue k="Engine check" v={<span className="num">Needs one asset</span>} />
        </div>
      </RailPanel>
      <p className="m-0 text-[12px] leading-[1.55] text-fg-3">
        A strategy needs at least one asset before the engine can check it. Saving creates version
        1; nothing trades until you start a session.
      </p>
    </div>
  );
}
