import { PhoneFrame, ScreenFrame } from '../components/ScreenFrame';
import { SectionArt } from '../components/SectionArt';
import { SectionDivider } from '../components/SectionDivider';
import { DIVIDER } from '../data/sections';

const STEPS = [
  'Describe the funds and the rule.',
  'Get a validated draft.',
  'Edit it as blocks or code.',
  'Backtest, then run it in paper or live.',
];

export function Copilot() {
  return (
    <section className="sec wrap" id="copilot">
      <SectionArt id="copilot" />
      <div className="split">
        <div className="rise">
          <SectionDivider label={DIVIDER.copilot} />
          <h2>Describe a strategy in plain English.</h2>
          <p>The copilot writes validated rules. Nothing runs until you accept.</p>
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li key={s}>
                <i aria-hidden="true">{i + 1}</i>
                {s}
              </li>
            ))}
          </ol>
        </div>
        <div className="cop-vis rise">
          <ScreenFrame screen="copilot" appHeight={560} />
          <PhoneFrame phone="copilot" className="ph" />
        </div>
      </div>
    </section>
  );
}
