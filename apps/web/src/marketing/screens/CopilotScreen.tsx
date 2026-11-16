import { AppNav, Code, Panel, WeightBar } from './parts';

const DRAFT = [
  '(strategy "Tech Momentum Rotation"',
  '  :rebalance monthly :benchmark QQQ',
  '  (filter :by momentum :select (top 2) :lookback 90',
  '    (weight :method equal',
  '      (asset QQQ) (asset XLK) (asset SMH))))',
];

const CHECKS = ['parsed', 'validated · 3 symbols', 'needs 90 bars of history', 'nothing saved yet'];

function Message({ who, children }: { who: 'You' | 'Copilot'; children: string }) {
  return (
    <div className={`msg ${who === 'You' ? 'me' : 'ai'}`}>
      <span className="who">{who}</span>
      <div className="bub">{children}</div>
    </div>
  );
}

export function CopilotScreen() {
  return (
    <>
      <AppNav on="Copilot" />
      <div className="app-main cop-main">
        <Panel title="Copilot" aside="strategy language v1">
          <div className="pn-b vgrid tight">
            <Message who="You">
              Build me a momentum rotation across tech ETFs, rebalanced monthly.
            </Message>
            <Message who="Copilot">
              Ranking QQQ, XLK and SMH by 90-day return each month and holding the top two at equal
              weight, with QQQ as the benchmark.
            </Message>
            <div className="art">
              <div className="flex items-center justify-between">
                <b>Tech Momentum Rotation</b>
                <span className="flex gap-1">
                  <span className="chip">Draft</span>
                  <span className="chip ok">Valid</span>
                  <span className="chip ok">Backtestable</span>
                </span>
              </div>
              <Code lines={DRAFT} className="flush" />
              <div className="flex gap-2">
                <span className="b p">Open in editor</span>
                <span className="b">Backtest</span>
                <span className="b">Discard</span>
              </div>
            </div>
            <Message who="You">What would it hold today?</Message>
            <Message who="Copilot">
              SMH and QQQ at 50% each. XLK ranks third on 90-day return, so it isn&apos;t held this
              month.
            </Message>
          </div>
        </Panel>
        <div className="vgrid">
          <Panel title="Would hold today">
            <div className="pn-b">
              <WeightBar
                parts={[
                  { shade: 'h1', weight: 50 },
                  { shade: 'h3', weight: 50 },
                ]}
              />
              <div className="leg mt-2">
                <span>
                  <b className="sym">SMH</b> 50%
                </span>
                <span>
                  <b className="sym">QQQ</b> 50%
                </span>
              </div>
            </div>
          </Panel>
          <Panel title="Checks">
            <div className="log">
              {CHECKS.map((x, i) => (
                <div key={x} className="one">
                  <span className={i < 3 ? 'ok' : 't3'}>{x}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
