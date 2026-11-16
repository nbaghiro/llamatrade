import { PhoneFrame, ScreenFrame } from '../components/ScreenFrame';
import { SectionArt } from '../components/SectionArt';
import { SectionDivider } from '../components/SectionDivider';
import { DIVIDER } from '../data/sections';
import type { ScreenName } from '../screens/registry';

const PANELS: readonly [ScreenName, string, string][] = [
  ['checks', 'Seven risk checks', 'A failed check stops the order and says why.'],
  ['orders', 'Sells first', 'Sales fund the buys.'],
  ['recon', 'Reconciliation', 'A mismatch freezes the sleeve.'],
];

export function Live() {
  return (
    <section className="sec wrap" id="live">
      <SectionArt id="live" />
      <div className="sec-h rise">
        <SectionDivider label={DIVIDER.live} />
        <h2>Paper and live sessions, step by step.</h2>
      </div>
      <p className="statement rise">
        What you backtest is what trades. <span>Same evaluation, sizing and dates.</span>
      </p>
      <div className="four rise">
        {PANELS.map(([screen, h, p]) => (
          <figure key={screen}>
            <ScreenFrame screen={screen} width={440} appHeight={450} bar={false} />
            <figcaption>
              <b>{h}</b>
              {p}
            </figcaption>
          </figure>
        ))}
        <figure>
          <div className="phonecell">
            <PhoneFrame phone="portfolio" />
          </div>
          <figcaption>
            <b>On your phone</b>
            Equity, sleeves and the copilot.
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
