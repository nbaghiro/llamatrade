import { Tokens } from '../components/CodeBlock';
import { k, m, p, s, type Tok } from '../components/codeTokens';

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
  p('\n'), m(';; compiled OK · 0 errors · backtestable'),
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
              <span>◈ COPILOT</span>
              <span>DSL v1</span>
            </div>
            <div className="cw-body">
              <div className="bubble me">
                <span className="who">You</span>Build me a momentum rotation across tech ETFs,
                rebalance monthly.
              </div>
              <div className="bubble ai">
                <span className="who">Copilot</span>Done. Filtering by 90-day momentum, holding the
                top 2 equal-weight across five tech ETFs, rebalanced monthly. Here&apos;s the
                compiled strategy:
                <div className="dsl" aria-hidden="true">
                  <Tokens segs={COPILOT_DSL} />
                </div>
              </div>
            </div>
            <div className="cw-foot">
              <span className="tag">✓ Valid</span>
              <span className="tag">✓ Backtestable</span>
              <span style={{ opacity: 0.6 }}>Editable before deploy</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
