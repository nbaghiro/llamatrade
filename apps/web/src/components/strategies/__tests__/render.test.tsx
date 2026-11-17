import { create } from '@bufbuild/protobuf';
import { StrategySchema } from '@llamatrade/core/proto/strategy_pb';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { StageTrackPhoneRow, StageTrackRow } from '../StageTrackTable';
import { StrategiesEmpty } from '../StrategiesEmpty';

const html = (node: React.ReactNode) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
const TODAY = new Date(Date.UTC(2026, 10, 17));
const strategy = create(StrategySchema, {
  id: 'st1',
  name: 'Recession Radar',
  version: 3,
  rebalance: 'monthly',
  symbols: ['TLT', 'GLD', 'VTI'],
});

describe('strategies render', () => {
  it('shows the three ways in over an empty track', () => {
    const out = html(<StrategiesEmpty />);
    expect(out).toContain('Start from a template');
    expect(out).toContain('Describe it to Copilot');
    expect(out).toContain('Build from blocks');
    expect(out).toContain('Your first strategy appears here as a draft');
    expect(out).toContain('Real money on Alpaca');
  });

  it('draws a draft row with its version and next step', () => {
    for (const Row of [StageTrackRow, StageTrackPhoneRow]) {
      const out = html(<Row strategy={strategy} sessions={[]} today={TODAY} onDeploy={() => {}} />);
      expect(out).toContain('Recession Radar');
      expect(out).toContain('Monthly · TLT GLD VTI');
    }
    const wide = html(
      <StageTrackRow strategy={strategy} sessions={[]} today={TODAY} onDeploy={() => {}} />
    );
    expect(wide).toContain('v3');
  });
});
