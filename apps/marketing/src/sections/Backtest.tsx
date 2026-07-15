import { useEffect, useRef } from 'react';

/** 02 · Backtest — result panel: equity curve, monthly heatmap, metrics. */

interface HeatCell {
  cls: string;
  val: string;
}
interface HeatRow {
  year: string;
  months: HeatCell[];
  yr: HeatCell;
}

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

const c = (cls: string, val: string): HeatCell => ({ cls, val });

const HEAT: HeatRow[] = [
  {
    year: '2022',
    months: [
      c('r', '-2.1'), c('r', '-0.8'), c('g', '+3.2'), c('r2', '-4.5'), c('r', '-1.2'),
      c('r2', '-5.8'), c('g2', '+6.1'), c('r2', '-3.0'), c('r2', '-6.2'), c('g2', '+5.4'),
      c('g2', '+4.1'), c('r', '-2.6'),
    ],
    yr: c('r2', '-5.9'),
  },
  {
    year: '2023',
    months: [
      c('g2', '+6.8'), c('r', '-1.4'), c('g', '+3.9'), c('g', '+1.2'), c('g2', '+4.7'),
      c('g2', '+5.1'), c('g', '+2.8'), c('r', '-2.3'), c('r2', '-3.1'), c('r', '-1.8'),
      c('g2', '+7.2'), c('g2', '+4.4'),
    ],
    yr: c('g2', '+31.4'),
  },
  {
    year: '2024',
    months: [
      c('g', '+2.9'), c('g2', '+5.2'), c('g', '+2.1'), c('r2', '-3.4'), c('g2', '+4.8'),
      c('g', '+3.3'), c('g', '+0.6'), c('r', '-1.9'), c('g', '+2.4'), c('g', '+1.1'),
      c('g2', '+5.6'), c('r', '-2.2'),
    ],
    yr: c('g2', '+21.8'),
  },
  {
    year: '2025',
    months: [
      c('g', '+3.1'), c('r', '-2.0'), c('g', '+1.4'), c('g', '+2.7'), c('g', '+3.6'),
      c('r', '-1.1'), c('g', '+2.9'), c('g', '+1.8'), c('r', '-0.7'), c('g2', '+4.2'),
      c('g', '+1.5'), c('g', '+2.3'),
    ],
    yr: c('g2', '+21.6'),
  },
];

const INDICATORS = [
  'SMA', 'EMA', 'RSI', 'MACD', 'BOLLINGER', 'ATR', 'ADX', 'STOCH', 'CCI', 'OBV', 'VWAP', 'MFI',
];

function useProgressFill() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fill = ref.current;
    if (!fill) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    if (reduce || !('IntersectionObserver' in window)) {
      fill.style.width = '100%';
      return;
    }
    let filled = false;
    const runFill = (): void => {
      if (filled) return;
      filled = true;
      fill.style.transition = 'width 1.6s cubic-bezier(.2,.8,.2,1)';
      requestAnimationFrame(() => {
        fill.style.width = '100%';
      });
    };
    let obs: IntersectionObserver | null = null;
    try {
      obs = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              runFill();
              obs?.disconnect();
            }
          });
        },
        { threshold: 0.25 }
      );
      obs.observe(fill);
    } catch {
      runFill();
    }
    const t = window.setTimeout(runFill, 2600);
    return () => {
      obs?.disconnect();
      window.clearTimeout(t);
    };
  }, []);
  return ref;
}

export function Backtest() {
  const fillRef = useProgressFill();

  return (
    <section id="backtest">
      <div className="wrap">
        <div className="sec-head reveal">
          <span className="sec-idx">02 / BACKTEST</span>
          <h2 className="sec-title">
            Prove it against
            <br />
            the tape.
          </h2>
          <span className="sec-lead">Live progress · Cancel anytime</span>
        </div>

        <div className="panel reveal">
          <div className="p-bar">
            <span className="run">
              <span className="d done" aria-hidden="true" /> BACKTEST COMPLETE ·
              momentum-rotation · Jan 2019 – Jan 2026
            </span>
            <span>
              <button className="btn-cancel" type="button">
                Re-run ↺
              </button>
            </span>
          </div>
          <div className="progress" aria-hidden="true">
            <div className="fill" ref={fillRef} />
          </div>
          <div className="bt-body">
            <div className="bt-chart">
              <div className="legend">
                <span className="k">
                  <span className="sw" /> STRATEGY
                </span>
                <span className="k">
                  <span className="sw b" /> BENCHMARK · SPY
                </span>
                <span className="k" style={{ marginLeft: 'auto', color: 'var(--orange)' }}>
                  +218% vs +96%
                </span>
              </div>
              <svg
                viewBox="0 0 600 240"
                role="img"
                aria-label="Equity curve: strategy compounding to plus 218 percent versus SPY benchmark plus 96 percent"
                preserveAspectRatio="none"
                style={{
                  width: '100%',
                  height: 'auto',
                  border: '2px solid var(--ink)',
                  background: 'var(--bone)',
                }}
              >
                <g stroke="rgba(13,13,13,.12)" strokeWidth="1">
                  <line x1="0" y1="60" x2="600" y2="60" />
                  <line x1="0" y1="120" x2="600" y2="120" />
                  <line x1="0" y1="180" x2="600" y2="180" />
                  <line x1="150" y1="0" x2="150" y2="240" />
                  <line x1="300" y1="0" x2="300" y2="240" />
                  <line x1="450" y1="0" x2="450" y2="240" />
                </g>
                <polyline
                  fill="none"
                  stroke="#0d0d0d"
                  strokeWidth="2.5"
                  strokeDasharray="7 6"
                  points="0,205 60,200 120,196 180,188 240,182 300,170 360,165 420,150 480,140 540,128 600,118"
                />
                <polyline
                  fill="none"
                  stroke="#ff4d1c"
                  strokeWidth="4"
                  strokeLinejoin="round"
                  points="0,205 60,196 120,184 180,190 240,158 300,148 360,120 420,132 480,92 540,70 600,40"
                />
                <circle cx="600" cy="40" r="6" fill="#ff4d1c" stroke="#0d0d0d" strokeWidth="2" />
              </svg>
              <div className="heat-wrap">
                <div className="heat-cap">Monthly returns · % · illustrative</div>
                <div className="heat-scroll">
                  <table className="heat" aria-label="Monthly returns tearsheet by year, illustrative">
                    <thead>
                      <tr>
                        <th scope="col">YR</th>
                        {MONTHS.map((mo) => (
                          <th key={mo} scope="col">
                            {mo}
                          </th>
                        ))}
                        <th scope="col">YEAR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {HEAT.map((row) => (
                        <tr key={row.year}>
                          <th scope="row">{row.year}</th>
                          {row.months.map((cell, i) => (
                            <td key={i} className={cell.cls}>
                              {cell.val}
                            </td>
                          ))}
                          <td className={`yr ${row.yr.cls}`}>{row.yr.val}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="metrics" role="table" aria-label="Backtest performance metrics">
              <div className="m">
                <div className="l">Sharpe</div>
                <div className="v acc">1.84</div>
              </div>
              <div className="m">
                <div className="l">Sortino</div>
                <div className="v acc">2.41</div>
              </div>
              <div className="m">
                <div className="l">CAGR</div>
                <div className="v pos">+18.0%</div>
              </div>
              <div className="m">
                <div className="l">Max drawdown</div>
                <div className="v neg">-14.2%</div>
              </div>
              <div className="m">
                <div className="l">Win rate</div>
                <div className="v">63%</div>
              </div>
              <div className="m">
                <div className="l">Total return</div>
                <div className="v pos">+218%</div>
              </div>
            </div>
          </div>
          <div className="bt-foot">
            <span>
              TRADES <b>146</b>
            </span>
            <span>
              REBALANCES <b>84</b>
            </span>
            <span>
              AVG HOLD <b>2.3 mo</b>
            </span>
            <span>
              UNIVERSE <b>5 ETFs</b>
            </span>
            <span>
              FEES + SLIPPAGE <b>MODELED</b>
            </span>
          </div>
        </div>

        <div className="ind-strip reveal" aria-label="Available indicators">
          {INDICATORS.map((ind) => (
            <span key={ind} className="chip">
              {ind}
            </span>
          ))}
          <span className="chip more">+ 5 MORE · MULTI-SYMBOL</span>
        </div>
      </div>
    </section>
  );
}
