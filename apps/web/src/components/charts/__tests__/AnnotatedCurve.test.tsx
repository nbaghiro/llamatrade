import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { AnnotatedCurve, LaneLegend } from '..';
import { ModeBadge, PaperLiveSplit, ScopeControl, StatList } from '../../ui';

const d = (s: string) => new Date(`${s}T16:00:00Z`);
const dates = [d('2026-08-17'), d('2026-09-15'), d('2026-10-15'), d('2026-11-17')];

const render = (node: JSX.Element) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

describe('AnnotatedCurve', () => {
  it('draws the curve, benchmark, pins, lanes, Now and the future column', () => {
    const html = render(
      <AnnotatedCurve
        label="Account equity"
        dates={dates}
        values={[100, 104, 101, 108]}
        benchmark={[100, 101, 102, 103]}
        now={{ label: 'Now 10:42' }}
        future={{ end: d('2026-12-01'), title: 'Next two weeks', ticks: [d('2026-12-01')] }}
        pins={[
          { at: d('2026-09-15'), label: 'Momentum Sectors started' },
          { at: d('2026-11-17'), label: 'Fills today', tone: 'accent', count: 3 },
        ]}
        lanes={[
          {
            id: 'aw',
            label: 'All-Weather Portfolio',
            badge: <ModeBadge mode="live" size="sm" />,
            events: [
              { at: d('2026-09-15'), shape: 'ring' },
              { at: d('2026-11-17'), shape: 'dot', count: 1 },
            ],
            future: { events: [{ at: d('2026-12-01'), shape: 'planned' }] },
          },
          {
            id: 'tm',
            label: 'Tech Momentum',
            tone: 'muted',
            spans: [{ from: d('2026-08-17'), to: d('2026-11-12'), style: 'off' }],
            events: [{ at: d('2026-11-12'), shape: 'stop' }],
            future: { note: 'Stopped, holding cash' },
          },
          { id: 'mo', label: 'Momentum Sectors', tone: 'risk' },
        ]}
        legend={[
          { shape: 'ring', label: 'Rebalance' },
          { shape: 'planned', label: 'Planned' },
        ]}
      />
    );
    expect(html).toContain('aria-label="Account equity"');
    expect(html.match(/<path/g)?.length).toBe(3);
    expect(html).toContain('stroke-dasharray="3 3"');
    expect(html).toContain('Momentum Sectors started');
    expect(html).toContain('Fills today');
    expect(html).toContain('Now 10:42');
    expect(html).toContain('Next two weeks');
    expect(html).toContain('Stopped, holding cash');
    expect(html).toContain('All-Weather Portfolio');
    expect(html).toContain('>Live<');
    expect(html).toContain('Rebalance');
    expect(html).toContain('Dec 1');
    expect(html).toContain('text-risk');
    expect(html).toContain('border-dashed');
  });

  it('draws without a future column, with bands and labelled bars', () => {
    const html = render(
      <AnnotatedCurve
        label="Backtest"
        dates={dates}
        values={[100, 98, 103, 110]}
        bands={[{ from: d('2026-09-01'), to: d('2026-10-01'), tone: 'loss', through: true }]}
        lanes={[
          {
            id: 'tlt',
            label: 'TLT',
            sub: '60% defensive',
            spans: [
              { from: d('2026-09-01'), to: d('2026-10-01'), style: 'bar', label: 'TLT, GLD' },
            ],
          },
        ]}
      />
    );
    expect(html).toContain('bg-loss/10');
    expect(html).toContain('TLT, GLD');
    expect(html).toContain('60% defensive');
    expect(html).not.toContain('Now');
  });

  it('copes with no data', () => {
    expect(() => render(<AnnotatedCurve label="Empty" dates={[]} values={[]} />)).not.toThrow();
  });
});

describe('shared pieces', () => {
  it('shows live and paper as figures, and a split bar', () => {
    const figures = render(<PaperLiveSplit live={48210.55} paper={80195.57} />);
    expect(figures).toContain('$48,210.55');
    expect(figures).toContain('$80,195.57');
    expect(figures).not.toContain('role="img"');
    const bar = render(<PaperLiveSplit live={25} paper={75} variant="bar" />);
    expect(bar).toContain('25.0% live, 75.0% paper');
    expect(render(<PaperLiveSplit live={0} paper={10} variant="bar" />)).toContain(
      '0.0% live, 100.0% paper'
    );
  });

  it('renders the scope as a radio group, or a label when there is one account', () => {
    const many = render(
      <ScopeControl
        value="live"
        onChange={() => undefined}
        options={[
          { key: 'all', label: 'All accounts', detail: '$128,406.12' },
          { key: 'live', label: 'Live ••4821' },
        ]}
      />
    );
    expect(many).toContain('role="radiogroup"');
    expect(many).toMatch(/aria-checked="true"[^>]*>.*Live ••4821/);
    expect(many).toContain('$128,406.12');
    const one = render(
      <ScopeControl
        value="paper"
        onChange={() => undefined}
        options={[{ key: 'paper', label: 'Paper ••PA92' }]}
      />
    );
    expect(one).not.toContain('radiogroup');
    expect(one).toContain('Paper ••PA92');
  });

  it('renders stats, badges and the legend', () => {
    const stats = render(
      <StatList items={[{ label: 'Max drawdown', value: '−2.31%', tone: 'loss' }]} />
    );
    expect(stats).toContain('text-loss');
    expect(render(<ModeBadge mode="paper" />)).toContain('border-dashed');
    expect(render(<LaneLegend items={[{ shape: 'ring', label: 'Rebalance' }]} />)).toContain(
      'Rebalance'
    );
    expect(render(<LaneLegend items={[]} />)).toBe('');
  });
});
