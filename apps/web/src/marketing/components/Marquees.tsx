import { Fragment } from 'react';

import { Marquee } from '../../components/common/Marquee';

/**
 * The three ticker rows.
 *
 * - <TopTicker> stays a bespoke marquee: its items carry per-symbol green/red
 *   up/down arrows, which the shared <Marquee>'s `string[]` items cannot express.
 *   (The original "or CSS" ticker path.)
 * - <FeatureMarquee> / <BottomMarquee> use the shared <Marquee> — plain text
 *   items + the Monolith asterisk separator — wrapped in the marketing bar chrome.
 */

interface Ticker {
  sym: string;
  dir: 'up' | 'down';
  pct: string;
}

const TICKER: Ticker[] = [
  { sym: 'SPY', dir: 'up', pct: '0.42%' },
  { sym: 'QQQ', dir: 'up', pct: '0.91%' },
  { sym: 'TSLA', dir: 'down', pct: '1.13%' },
  { sym: 'NVDA', dir: 'up', pct: '2.07%' },
  { sym: 'AAPL', dir: 'down', pct: '0.28%' },
  { sym: 'MSFT', dir: 'up', pct: '0.66%' },
  { sym: 'AMD', dir: 'up', pct: '1.44%' },
  { sym: 'SMH', dir: 'up', pct: '0.88%' },
  { sym: 'ARKK', dir: 'down', pct: '2.31%' },
  { sym: 'IWM', dir: 'up', pct: '0.19%' },
];

export function TopTicker() {
  return (
    <div
      className="marquee fast"
      role="marquee"
      aria-label="Live market ticker of illustrative symbols"
    >
      <div className="track" aria-hidden="false">
        {[0, 1].map((copy) =>
          TICKER.map((it, i) => (
            <Fragment key={`${copy}-${i}`}>
              <span>
                {it.sym}{' '}
                <span className={it.dir}>
                  {it.dir === 'up' ? '▲' : '▼'} {it.pct}
                </span>
              </span>
              <span className="sep">/</span>
            </Fragment>
          ))
        )}
      </div>
    </div>
  );
}

const FEATURE_ITEMS = [
  'VISUAL BLOCK BUILDER',
  'S-EXPRESSION DSL',
  'AI COPILOT',
  'SHARPE / SORTINO',
  'MAX DRAWDOWN',
  'EQUITY CURVE',
  'MONTHLY GRID',
  'LIVE = BACKTEST',
  'DOUBLE-ENTRY LEDGER',
  'OPEN SOURCE',
];

const BOTTOM_ITEMS = [
  'BUILD',
  'BACKTEST',
  'PAPER + LIVE',
  'MONITOR',
  'OWN YOUR ACCOUNT',
  'LIVE = BACKTEST',
  'ENCRYPTED KEYS',
  'OPEN SOURCE',
  'NO BLACK BOX',
];

/** Asterisk separator that inherits the bar's text color (ink on orange, bone on ink). */
const STAR = (
  <span aria-hidden="true" className="px-[22px]">
    ✱
  </span>
);

export function FeatureMarquee() {
  return (
    <div className="mkt-marquee accent" aria-label="Feature keywords">
      <Marquee
        items={FEATURE_ITEMS}
        speed={42}
        separator={STAR}
        trackClassName="[animation-direction:reverse]"
      />
    </div>
  );
}

export function BottomMarquee() {
  return (
    <div className="mkt-marquee" aria-label="Feature keywords ticker">
      <Marquee items={BOTTOM_ITEMS} speed={42} separator={STAR} />
    </div>
  );
}
