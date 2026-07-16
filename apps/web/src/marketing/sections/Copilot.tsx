import { Tokens } from '../components/CodeBlock';
import { k, p, s, type Tok } from '../components/codeTokens';

/** 03 · Copilot — plain-English → DSL, shown as a chat window. */

// The compiled strategy inside the copilot reply bubble (`.dsl`, white-space:
// pre-wrap — newlines + indentation live in the token strings).
const COPILOT_DSL: Tok[] = [
  k('(strategy'), p(' '), s('"Tech Momentum Rotation"'),
  p('\n  '), k(':rebalance'), p(' monthly'),
  p('\n  '), k(':benchmark'), p(' '), s('QQQ'),
  p('\n  '), k('(filter'), p(' '), k(':by'), p(' momentum '), k(':select'), p(' (top 2) '),
  k(':lookback'), p(' 90'),
  p('\n    '), k('(weight'), p(' '), k(':method'), p(' equal'),
  p('\n      '), k('(asset'), p(' '), s('QQQ)'),
  p('\n      '), k('(asset'), p(' '), s('XLK)'),
  p('\n      '), k('(asset'), p(' '), s('SMH)'),
  p('\n      '), k('(asset'), p(' '), s('SOXX)'),
  p('\n      '), k('(asset'), p(' '), s('VGT))))'),
];

export function Copilot() {
  return (
    <section id="copilot">
      <div className="wrap">
        <div className="sec-head reveal">
          <span className="sec-idx">03 / COPILOT</span>
          <h2 className="sec-title">
            Say it.
            <br />
            Ship the DSL.
          </h2>
          <span className="sec-lead">Plain English → valid strategy</span>
        </div>

        <div className="copilot">
          <div className="cop-left reveal">
            <p>
              The AI copilot doesn&apos;t hand you a black box. It translates plain English into the{' '}
              <b>same DSL</b> you&apos;d write by hand — fully readable, editable, and backtestable
              before a single share moves.
            </p>
            <div className="cop-steps">
              <div className="st">
                <span className="n">01</span>
                <span>
                  <b>Describe intent</b>Write what you want in one sentence.
                </span>
              </div>
              <div className="st">
                <span className="n">02</span>
                <span>
                  <b>Generate valid DSL</b>The copilot compiles it and reports errors up front.
                </span>
              </div>
              <div className="st">
                <span className="n">03</span>
                <span>
                  <b>Inspect &amp; edit</b>Read every rule. Tweak weights, filters, assets.
                </span>
              </div>
              <div className="st">
                <span className="n">04</span>
                <span>
                  <b>Backtest, then deploy</b>Prove it, rehearse in paper, then go live for real.
                </span>
              </div>
            </div>
          </div>

          <div className="chatwin reveal" data-d="1" aria-label="AI copilot conversation">
            <div className="cw-bar">
              <span>◆ Copilot</span>
              <span>DSL v1</span>
            </div>
            <div className="cw-body">
              {/* User */}
              <div className="cmsg me">
                <div className="cmsg-col">
                  <span className="cmsg-who">You</span>
                  <div className="cbub me">
                    Build me a momentum rotation across tech ETFs, rebalance monthly.
                  </div>
                </div>
                <div className="cav me" aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="12" cy="7.5" r="4" />
                    <path d="M12 14c-4.4 0-8 2.7-8 6v1h16v-1c0-3.3-3.6-6-8-6z" />
                  </svg>
                </div>
              </div>

              {/* Copilot */}
              <div className="cmsg ai">
                <div className="cav ai" aria-hidden="true">✦</div>
                <div className="cmsg-col">
                  <span className="cmsg-who">Copilot</span>
                  <div className="cbub ai">
                    Done — filtering by 90-day momentum, holding the <b>top 2 equal-weight</b> across
                    five tech ETFs, rebalanced monthly.
                  </div>

                  {/* Inline strategy artifact */}
                  <div className="artifact" aria-label="Generated strategy">
                    <div className="art-head">
                      <span className="art-kind">✦ Strategy</span>
                      <span className="art-name">Tech Momentum Rotation</span>
                      <span className="art-badge">Draft</span>
                    </div>
                    <div className="art-meta">Rebalance monthly · Benchmark QQQ · 5 assets</div>
                    <div className="art-dsl" aria-hidden="true">
                      <Tokens segs={COPILOT_DSL} />
                    </div>
                    <div className="art-status">
                      <span className="ok">✓ Valid</span>
                      <span className="ok">✓ Backtestable</span>
                    </div>
                    <button className="art-save" type="button">
                      ✦ Save strategy
                    </button>
                    <span className="art-hint">Open in the desktop builder to edit or backtest</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
