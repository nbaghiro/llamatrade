import { SectionArt } from '../components/SectionArt';
import { SectionDivider } from '../components/SectionDivider';
import { DIVIDER } from '../data/sections';

const CARDS: readonly [string, string][] = [
  ['Alpaca holds your funds', 'LlamaTrade places orders and never holds money.'],
  ['Encrypted keys', 'Encrypted at rest, scoped per session.'],
  ['Books that balance', 'A ledger sleeve per strategy, reconciled with Alpaca.'],
  ['Paper or live', 'Start in paper, then go live on your Alpaca account.'],
];

export function Own() {
  return (
    <section className="sec wrap" id="own">
      <SectionArt id="own" />
      <div className="sec-h rise">
        <SectionDivider label={DIVIDER.own} />
        <h2>Your keys. Your account.</h2>
        <p>LlamaTrade automates an account you own.</p>
      </div>
      <div className="own rise">
        {CARDS.map(([h, p]) => (
          <div key={h}>
            <h3>{h}</h3>
            <p>{p}</p>
          </div>
        ))}
      </div>
      <div className="loop rise">
        <b>Build</b>
        <i aria-hidden="true">→</i>
        <b>Backtest</b>
        <i aria-hidden="true">→</i>
        <b>Deploy</b>
        <i aria-hidden="true">→</i>
        <b>Monitor</b>
        <i aria-hidden="true">↺</i>
        <span>edit, version, redeploy</span>
      </div>
    </section>
  );
}
