import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { SetupRanges } from '../SetupRanges';

const config = {
  strategyId: 's1',
  startDate: '2021-10-30',
  endDate: '2026-10-30',
  initialCapital: 25000,
  symbols: [],
  commission: 1,
  slippage: 0.0005,
  timeframe: '1D',
  benchmarkSymbol: 'SPY',
};

describe('SetupRanges', () => {
  it('asks the question, offers four ranges and lists where it was tested', () => {
    const out = renderToStaticMarkup(
      <MemoryRouter>
        <SetupRanges
          strategyName="Recession Radar"
          strategyId="s1"
          versionLine="v4"
          config={config}
          onChange={() => undefined}
          rebalance="monthly"
          runs={[]}
          metrics={{}}
          today={new Date('2026-10-30T00:00:00Z')}
        />
      </MemoryRouter>
    );
    expect(out).toContain('What should Recession Radar be tested on?');
    expect(out).toContain('Through the 2022 fall');
    expect(out).toContain('aria-checked="true"');
    expect(out).toContain('61 rebalances');
    expect(out).toContain('$1.00 per fill + 0.05%');
    expect(out).toContain('No timed runs yet to estimate from');
    expect(out.match(/Not tested yet/g)).toHaveLength(4);
  });
});
