import type { ReactNode } from 'react';

/** 05 · Own it — custody / security / books / open-source + the core loop. */

interface OwnCard {
  no: string;
  title: string;
  body: string;
  icon: ReactNode;
}

const OWN_CARDS: OwnCard[] = [
  {
    no: 'A · CUSTODY',
    title: 'Bring your own keys',
    body: 'Connect your Alpaca API keys. LlamaTrade automates your account and never holds a cent of your money.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="#0d0d0d" strokeWidth="2.4" strokeLinecap="square">
        <rect x="4" y="10" width="16" height="10" />
        <path d="M8 10 V7 a4 4 0 0 1 8 0 v3" />
      </svg>
    ),
  },
  {
    no: 'B · SECURITY',
    title: 'Encrypted credentials',
    body: "Keys are encrypted at rest and scoped per session. Test risk-free in paper, then go live with real money when you're ready.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="#0d0d0d" strokeWidth="2.4" strokeLinecap="square">
        <path d="M12 3 L20 6 v6 c0 5-4 8-8 9-4-1-8-4-8-9 V6 Z" />
        <path d="M9 12 l2 2 4-4" />
      </svg>
    ),
  },
  {
    no: 'C · BOOKS',
    title: 'Accurate ledger',
    body: 'A double-entry portfolio ledger with sleeves and FIFO lots, reconciled against the broker every fill.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="#0d0d0d" strokeWidth="2.4" strokeLinecap="square">
        <path d="M4 5 h16 M4 12 h16 M4 19 h10" />
        <path d="M17 16 l3 3 -3 3" transform="translate(0,-3)" />
      </svg>
    ),
  },
  {
    no: 'D · OPEN SOURCE',
    title: 'No black box',
    body: 'Inspect the code, self-host it, trust it. The whole engine is open source — audit every decision it makes.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="#0d0d0d" strokeWidth="2.4" strokeLinecap="square">
        <path d="M9 4 L4 12 l5 8 M15 4 l5 8 -5 8" />
      </svg>
    ),
  },
];

interface LoopStep {
  n: string;
  t: string;
  d: string;
}

const LOOP: LoopStep[] = [
  { n: '→ 01', t: 'Build', d: 'No-code, DSL, or plain English.' },
  { n: '→ 02', t: 'Backtest', d: 'Sharpe, drawdown, equity curve.' },
  { n: '→ 03', t: 'Deploy', d: 'Rehearse in paper, then go live.' },
  { n: '→ 04', t: 'Monitor', d: 'Fills & P&L in real time.' },
];

export function OwnIt() {
  return (
    <section id="own">
      <div className="wrap">
        <div className="sec-head reveal">
          <span className="sec-idx">05 / OWN IT</span>
          <h2 className="sec-title">
            Your keys.
            <br />
            Your account.
            <br />
            Your call.
          </h2>
          <span className="sec-lead">We never custody your money</span>
        </div>

        <div className="own-grid reveal">
          {OWN_CARDS.map((card) => (
            <div className="oc" key={card.no}>
              <div className="ic" aria-hidden="true">
                {card.icon}
              </div>
              <span className="no">{card.no}</span>
              <h4>{card.title}</h4>
              <p>{card.body}</p>
            </div>
          ))}
        </div>

        <div className="kicker reveal" style={{ marginTop: 56, marginBottom: 18 }}>
          THE CORE LOOP
        </div>
        <div className="loop reveal">
          {LOOP.map((step) => (
            <div className="step" key={step.n}>
              <span className="n">{step.n}</span>
              <span className="t">{step.t}</span>
              <span className="d">{step.d}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
