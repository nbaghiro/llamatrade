import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { exampleBacktest } from '../../../lib/illustrative';
import { DrawdownBand, LineChart, MonthlyGrid, Sparkline } from '../../charts';
import { Logo } from '../../common/Logo';
import { AppearancePicker } from '../../settings/AppearancePicker';
import {
  AttentionLine,
  EmptyState,
  Money,
  NoMatch,
  PanelError,
  Pct,
  SkeletonChart,
  SkeletonRows,
  StatusMark,
  WeightBar,
} from '../../ui';
import { MobileTabBar } from '../MobileTabBar';
import { TopBar } from '../TopBar';

const at = (path: string, node: JSX.Element) =>
  renderToStaticMarkup(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);

describe('shell', () => {
  it('renders the six destinations, search, Paper and the market chip', () => {
    const html = at('/strategies/abc', <TopBar />);
    for (const label of ['Home', 'Portfolio', 'Strategies', 'Backtests', 'Sessions', 'Copilot']) {
      expect(html).toContain(`>${label}</a>`);
    }
    expect(html).toContain('Search or jump to');
    expect(html).toContain('>Paper<');
    expect(html).toMatch(/Market (open|closed)|Pre-market|After hours/);
    expect(html).toMatch(/aria-current="page"[^>]*>Strategies</);
    expect(html).not.toContain('Wallet');
    expect(html).not.toContain('Create');
  });

  it('marks Strategies active on a phone for backtests', () => {
    const html = at('/backtest', <MobileTabBar />);
    expect(html).toMatch(/aria-current="page"[^>]*>.*Strategies<\/a>/);
    expect(html).toContain('Account');
  });

  it('renders the Candlesticks mark with the accent candle', () => {
    const html = renderToStaticMarkup(<Logo showText />);
    expect(html).toContain('M8 2v20M12.4 13v16.5M25.6 13v16.5M16.8 12.5v10M21.2 13v9');
    expect(html).toContain('rgb(var(--accent))');
    expect(html).toContain('LlamaTrade');
  });

  it('renders the appearance picker with twelve accents', () => {
    const html = renderToStaticMarkup(<AppearancePicker />);
    expect(html).toContain('System');
    expect(html.match(/role="radio" aria-checked="(true|false)" aria-label=/g)).toHaveLength(12);
  });
});

describe('ui kit', () => {
  it('colours money only when it is profit and loss', () => {
    expect(renderToStaticMarkup(<Money value={-5} />)).not.toContain('text-loss');
    expect(renderToStaticMarkup(<Money value={-5} pnl />)).toContain('text-loss');
    expect(renderToStaticMarkup(<Pct value={0.0087} pnl />)).toContain('+0.87%');
  });

  it('shows frozen in amber', () => {
    expect(renderToStaticMarkup(<StatusMark state="frozen" />)).toContain('text-risk');
    expect(renderToStaticMarkup(<StatusMark state="running" />)).not.toContain('text-risk');
  });

  it('collapses several attention items into a count', () => {
    const html = renderToStaticMarkup(
      <AttentionLine
        items={[
          { id: 'a', title: 'A is frozen.' },
          { id: 'b', title: 'B was rejected.' },
        ]}
      />
    );
    expect(html).toContain('2 things need attention');
    expect(renderToStaticMarkup(<AttentionLine items={[]} />)).toBe('');
  });

  it('renders state panels', () => {
    expect(
      renderToStaticMarkup(<PanelError title="Couldn't load" onRetry={() => undefined} />)
    ).toContain('Try again');
    expect(renderToStaticMarkup(<EmptyState title="No strategies yet" />)).toContain(
      'No strategies yet'
    );
    expect(
      renderToStaticMarkup(<NoMatch noun="strategies" query="TLT" onClear={() => undefined} />)
    ).toContain('Clear filters');
    expect(renderToStaticMarkup(<SkeletonRows rows={2} />)).toContain('animate-pulse');
    expect(renderToStaticMarkup(<SkeletonChart />)).toContain('border-dashed');
    expect(renderToStaticMarkup(<SkeletonChart />)).not.toContain('<path');
  });

  it('clamps weight bars and places the target tick', () => {
    const html = renderToStaticMarkup(<WeightBar weight={1.4} target={0.5} />);
    expect(html).toContain('width:100%');
    expect(html).toContain('left:50%');
  });
});

describe('charts', () => {
  const bt = exampleBacktest();

  it('renders the example backtest', () => {
    const line = renderToStaticMarkup(
      <LineChart
        label="Equity"
        dates={bt.days}
        series={[
          { values: bt.benchmarkValues, kind: 'bench' },
          { values: bt.strategy, kind: 'main', area: true },
        ]}
      />
    );
    expect(line.match(/<path/g)?.length).toBe(3);
    expect(renderToStaticMarkup(<DrawdownBand dates={bt.days} drawdown={bt.drawdown} />)).toContain(
      '0%'
    );
    expect(renderToStaticMarkup(<MonthlyGrid months={bt.months} />)).toContain('2025');
    expect(renderToStaticMarkup(<Sparkline values={[1, 2, 3]} />)).toContain('path');
  });
});
