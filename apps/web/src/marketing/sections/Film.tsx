import { FilmStrip, type FilmFrame } from '../components/FilmStrip';
import { SectionDivider } from '../components/SectionDivider';
import { DIVIDER } from '../data/sections';

const FRAMES: readonly FilmFrame[] = [
  { screen: 'templates', title: 'Templates', caption: 'About 80 to start from.' },
  { screen: 'strategies', title: 'Strategies', caption: 'Every strategy and its state.' },
  { screen: 'editor', title: 'Strategy editor', caption: 'Blocks beside the source.' },
  { screen: 'copilot', title: 'Copilot', caption: 'A sentence becomes a draft.' },
  { screen: 'backtest', title: 'Backtest', caption: 'Equity, drawdown and months.' },
  { screen: 'session', title: 'Session', caption: 'Positions, orders, checks.' },
  { screen: 'portfolio', title: 'Portfolio', caption: 'Sleeves and cash.' },
  { screen: 'trades', title: 'Trades', caption: 'Every simulated order.' },
  { screen: 'broker', title: 'Broker connection', caption: 'Your Alpaca account, paper or live.' },
];

export function Film() {
  return (
    <section className="filmsec" id="film">
      <div className="wrap sec-h rise">
        <SectionDivider label={DIVIDER.film} />
        <h2>The app, screen by screen</h2>
      </div>
      <FilmStrip frames={FRAMES} />
    </section>
  );
}
