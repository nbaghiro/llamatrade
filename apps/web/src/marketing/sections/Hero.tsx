/** 01 · Hero — headline slab + strategy DSL terminal (three example strategies). */

type TCls = 'c-key' | 'c-sym' | 'c-mut' | 'div' | 'tp' | 'ta' | 'cur';
interface TSeg {
  c?: TCls;
  t: string;
}

const g = (c: TCls, t: string): TSeg => ({ c, t });
const r = (t: string): TSeg => ({ t });
const ind = (n: number): TSeg => ({ t: ' '.repeat(n) });
const CUR: TSeg = { c: 'cur', t: '' };

// The strategy.lt terminal, ported line-for-line from the static page. Each
// inner array is one `.ln` row. The DSL is valid libs/dsl grammar.
const TERMINAL: TSeg[][] = [
  [g('c-mut', '# the exact code you backtest is the code that trades live.')],
  [g('c-mut', '# three strategies, one language:')],
  [ind(1)],
  [g('div', ';; 01 · momentum rotation')],
  [g('tp', '('), g('c-key', 'strategy'), r(' '), g('c-sym', '"Tech Momentum Rotation"')],
  [ind(2), g('ta', ':rebalance'), r(' monthly '), g('ta', ':benchmark'), r(' '), g('c-sym', 'QQQ')],
  [
    ind(2),
    g('tp', '('),
    g('c-key', 'filter'),
    r(' '),
    g('ta', ':by'),
    r(' momentum '),
    g('ta', ':select'),
    r(' '),
    g('tp', '('),
    r('top 2'),
    g('tp', ')'),
    r(' '),
    g('ta', ':lookback'),
    r(' 90'),
  ],
  [ind(4), g('tp', '('), g('c-key', 'weight'), r(' '), g('ta', ':method'), r(' equal')],
  [
    ind(6),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'QQQ'),
    g('tp', ')'),
    r(' '),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'XLK'),
    g('tp', ')'),
    r(' '),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'SMH'),
    g('tp', '))))'),
  ],
  [ind(1)],
  [g('div', ';; 02 · trend crossover')],
  [
    g('tp', '('),
    g('c-key', 'strategy'),
    r(' '),
    g('c-sym', '"Golden Cross"'),
    r(' '),
    g('ta', ':rebalance'),
    r(' daily '),
    g('ta', ':benchmark'),
    r(' '),
    g('c-sym', 'SPY'),
  ],
  [
    ind(2),
    g('tp', '('),
    g('c-key', 'if'),
    r(' '),
    g('tp', '('),
    g('c-key', 'crosses-above'),
    r(' '),
    g('tp', '('),
    g('c-sym', 'ema'),
    r(' '),
    g('c-sym', 'SPY'),
    r(' 50'),
    g('tp', ')'),
    r(' '),
    g('tp', '('),
    g('c-sym', 'ema'),
    r(' '),
    g('c-sym', 'SPY'),
    r(' 200'),
    g('tp', '))'),
  ],
  [
    ind(4),
    g('tp', '('),
    g('c-key', 'weight'),
    r(' '),
    g('ta', ':method'),
    r(' equal '),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'SPY'),
    g('tp', '))'),
  ],
  [
    ind(4),
    g('tp', '('),
    g('c-key', 'else'),
    r(' '),
    g('tp', '('),
    g('c-key', 'weight'),
    r(' '),
    g('ta', ':method'),
    r(' equal '),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'BIL'),
    g('tp', ')))))'),
  ],
  [ind(1)],
  [g('div', ';; 03 · classic allocation')],
  [
    g('tp', '('),
    g('c-key', 'strategy'),
    r(' '),
    g('c-sym', '"Classic 60/40"'),
    r(' '),
    g('ta', ':rebalance'),
    r(' quarterly '),
    g('ta', ':benchmark'),
    r(' '),
    g('c-sym', 'AGG'),
  ],
  [ind(2), g('tp', '('), g('c-key', 'weight'), r(' '), g('ta', ':method'), r(' specified')],
  [
    ind(4),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'VOO'),
    r(' '),
    g('ta', ':weight'),
    r(' 60'),
    g('tp', ')'),
  ],
  [
    ind(4),
    g('tp', '('),
    g('c-key', 'asset'),
    r(' '),
    g('c-sym', 'BND'),
    r(' '),
    g('ta', ':weight'),
    r(' 40'),
    g('tp', ')))'),
  ],
  [ind(1)],
  [g('c-mut', '> compiled OK · 3 strategies · 0 errors'), r(' '), CUR],
];

function TerminalSeg({ seg }: { seg: TSeg }) {
  if (seg.c === 'cur') return <span className="cur" aria-hidden="true" />;
  if (seg.c) return <span className={seg.c}>{seg.t}</span>;
  return <span>{seg.t}</span>;
}

export function Hero() {
  return (
    <section className="hero" id="top">
      <div className="wrap">
        <div className="hero-grid">
          <div className="hero-left">
            <span className="hero-badge">
              <span className="dot" aria-hidden="true" /> Closed beta · Invite only · Test free → go
              live
            </span>
            <h1>
              BUILD THE
              <br />
              <span className="slab">MACHINE.</span>
              <br />
              <span className="outline">TRADE</span> <span className="o">YOUR</span>
              <br />
              OWN ACCOUNT.
            </h1>
            <p className="hero-sub">
              Open-source algorithmic trading for people who want the <b>engine</b>, not the pitch.
              Build a strategy three ways, backtest it hard, then run it on{' '}
              <b>your own Alpaca account</b> — rehearse risk-free in paper, then go live with real
              money.
            </p>
            <div className="hero-actions">
              <a className="btn btn-primary" href="#join">
                Start free <span className="arr">→</span>
              </a>
              <a className="btn" href="#">
                View on GitHub
              </a>
            </div>
            <div className="hero-meta">
              <div className="cell">
                <div className="n">16+</div>
                <div className="l">Indicators wired</div>
              </div>
              <div className="cell">
                <div className="n">3</div>
                <div className="l">Ways to build</div>
              </div>
              <div className="cell">
                <div className="n">$0</div>
                <div className="l">Free to test-drive</div>
              </div>
            </div>
          </div>
          <div className="hero-right">
            <div className="colnums" aria-hidden="true">
              {['01', '02', '03', '04', '05', '06', '07', '08'].map((n) => (
                <span key={n}>{n}</span>
              ))}
            </div>
            <div className="terminal" aria-label="Strategy DSL preview">
              <div className="bar">
                <span className="b" aria-hidden="true" /> strategy.lt · examples
              </div>
              {TERMINAL.map((line, i) => (
                <div className="ln" key={i}>
                  {line.map((seg, j) => (
                    <TerminalSeg key={j} seg={seg} />
                  ))}
                </div>
              ))}
              <div className="term-foot">
                <span>strategy.lt</span>
                <span>LlamaTrade DSL · v1</span>
                <span>0 errors · UTF-8</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
