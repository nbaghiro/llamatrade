import { InviteForm } from '../components/InviteForm';
import { SectionArt } from '../components/SectionArt';
import { SectionDivider } from '../components/SectionDivider';
import { DIVIDER } from '../data/sections';

export function Join() {
  return (
    <section className="cta wrap rise" id="join">
      <SectionArt id="join" />
      <SectionDivider label={DIVIDER.join} />
      <h2>Stop guessing. Start testing.</h2>
      <p>Paper and live trading on your own Alpaca account. Places open in small groups.</p>
      <InviteForm id="join-invite" />
      <p className="fine">Market data from Alpaca&apos;s IEX feed, about 3% of US volume.</p>
    </section>
  );
}
