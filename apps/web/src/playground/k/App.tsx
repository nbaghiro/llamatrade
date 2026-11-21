import { useEffect, type ReactNode } from 'react';
import { matchPath, useLocation, useSearchParams } from 'react-router-dom';

import { BACKTESTS, SESSIONS, strategyById } from '../data';

import { AskLine, AskProvider, Palette } from './ask';
import { useAsk } from './askContext';
import { BacktestPanel, BacktestsLeft } from './backtests';
import { HoldingsPanel, PortfolioLeft } from './portfolio';
import { SessionPanel, SessionsLeft } from './sessions';
import { Shell } from './shell';
import { BuilderPanel, StrategiesLeft } from './strategies';
import { AccountPanel, TodayLeft } from './today';

interface Page {
  tab: string;
  pan: number;
  rail: ReactNode;
  cardKey: string;
  card: ReactNode;
  context?: string;
  placeholder: string;
  suggestions: string[];
}

function usePage(): Page {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const param = (pattern: string) => matchPath(pattern, pathname)?.params.id;

  if (pathname.startsWith('/k/strategies')) {
    const id = param('/k/strategies/:id') ?? 'recession-radar';
    const s = strategyById(id) ?? strategyById('recession-radar');
    if (!s) throw new Error('missing strategy');
    return {
      tab: 'Strategies',
      pan: 1,
      rail: <StrategiesLeft sel={s.id} />,
      cardKey: `strategy:${s.id}`,
      card: <BuilderPanel key={s.id} s={s} />,
      context: s.id,
      placeholder: `Ask about ${s.name}, or describe an edit`,
      suggestions: [`Explain ${s.name}`, `Suggest a safer edit to ${s.name}`],
    };
  }
  if (pathname.startsWith('/k/backtests')) {
    const id = param('/k/backtests/:id') ?? BACKTESTS[1].id;
    const b = BACKTESTS.find((x) => x.id === id) ?? BACKTESTS[1];
    return {
      tab: 'Backtests',
      pan: 2,
      rail: <BacktestsLeft sel={b.id} />,
      cardKey: `backtest:${b.id}`,
      card: <BacktestPanel id={b.id} />,
      context: b.strategyId,
      placeholder: 'Ask about a run, or what to test next',
      suggestions: ['Explain this run', 'Draft a trend strategy on QQQ'],
    };
  }
  if (pathname.startsWith('/k/sessions')) {
    const id = param('/k/sessions/:id') ?? 's-rr';
    const s = SESSIONS.find((x) => x.id === id) ?? SESSIONS[1];
    return {
      tab: 'Sessions',
      pan: 3,
      rail: <SessionsLeft sel={s.id} />,
      cardKey: `session:${s.id}`,
      card: <SessionPanel s={s} full />,
      context: s.strategyId,
      placeholder: 'Ask about a session',
      suggestions: ['Why is the account down today?', 'Why does it hold this?'],
    };
  }
  if (pathname.startsWith('/k/portfolio')) {
    const v = params.get('v') ?? 'account';
    return {
      tab: 'Portfolio',
      pan: 4,
      rail: <PortfolioLeft sel={v} />,
      cardKey: `portfolio:${v}`,
      card: v === 'account' ? <AccountPanel eyebrow="Portfolio" /> : <HoldingsPanel cls={v} />,
      placeholder: 'Ask about the account, holdings or risk',
      suggestions: ['Why is the account down today?', 'Lower Recession Radar’s gold to 30%'],
    };
  }
  const sel = params.get('s') ?? 'account';
  const ses = SESSIONS.find((x) => x.id === sel);
  return {
    tab: 'Today',
    pan: 0,
    rail: <TodayLeft sel={ses ? ses.id : 'account'} />,
    cardKey: ses ? `session:${ses.id}` : 'account',
    card: ses ? <SessionPanel s={ses} /> : <AccountPanel />,
    context: ses?.strategyId,
    placeholder: 'Ask about your account, or describe a strategy',
    suggestions: [
      'Why is the account down today?',
      'Lower Recession Radar’s gold to 30%',
      'Draft a trend strategy on QQQ',
    ],
  };
}

function Frame() {
  const page = usePage();
  const { open, setOpen } = useAsk();
  const { pathname } = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [pathname, setOpen]);
  useEffect(() => {
    if (open) window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [open]);

  return (
    <Shell
      pan={page.pan}
      railKey={page.tab}
      rail={page.rail}
      cardKey={page.cardKey}
      card={page.card}
      askLine={<AskLine placeholder={page.placeholder} />}
      paletteOpen={open}
      onClosePalette={() => setOpen(false)}
      palette={
        <Palette
          key={page.tab}
          context={page.context}
          placeholder={page.placeholder}
          suggestions={page.suggestions}
          back={page.tab}
        />
      }
    />
  );
}

/** Option K: the card over the art on the left, a quiet ledger rail on the right, ⌘K over the card. */
export default function App() {
  return (
    <AskProvider>
      <Frame />
    </AskProvider>
  );
}
