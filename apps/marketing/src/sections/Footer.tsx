/** Footer — brand blurb, link columns, risk disclaimer, legal strip. */
export function Footer() {
  return (
    <footer>
      <div className="wrap">
        <div className="foot-top">
          <div className="foot-brand">
            <div className="name">LlamaTrade</div>
            <div className="tag">Open · Algorithmic · Your account</div>
            <p>
              The open-source machine for individual traders who automate their own account. Build,
              backtest, deploy, monitor.
            </p>
          </div>
          <div className="fcol">
            <h5>Product</h5>
            <a href="#build">Block builder</a>
            <a href="#copilot">AI copilot</a>
            <a href="#backtest">Backtesting</a>
            <a href="#live">Paper &amp; live trading</a>
          </div>
          <div className="fcol">
            <h5>Build with us</h5>
            <a href="#">View on GitHub</a>
            <a href="#">Read the docs</a>
            <a href="#">The DSL reference</a>
            <a href="#">Self-host guide</a>
          </div>
          <div className="fcol">
            <h5>Access</h5>
            <a href="#join">Join the beta</a>
            <a href="#join">Start free</a>
            <a href="#join">Connect Alpaca</a>
            <a href="#">Community</a>
          </div>
        </div>

        <div className="disclaimer">
          <p>
            <span className="warn">DISCLAIMER —</span> LlamaTrade automates your own brokerage
            account — you hold the funds, not us. Practice risk-free in paper mode, then go live with
            real money when you&apos;re ready. Live trading involves risk of loss. Not investment
            advice.
          </p>
        </div>

        <div className="foot-legal">
          <span>© LlamaTrade 2026 · Open source</span>
          <span className="badge">Closed beta · Invite only</span>
        </div>
      </div>
    </footer>
  );
}
