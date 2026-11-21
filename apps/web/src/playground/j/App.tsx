import { useEffect, type ReactNode } from 'react';
import { matchPath, useLocation, useSearchParams } from 'react-router-dom';

import { BACKTESTS, SESSIONS, strategyById } from '../data';

import { AskProvider, Composer, Conversation } from './ask';
import { useAsk } from './askContext';
import { BacktestPanel, BacktestsLeft } from './backtests';
import { HoldingsPanel, PortfolioLeft } from './portfolio';
import { SessionPanel, SessionsLeft } from './sessions';
import { Shell } from './shell';
import { BuilderPanel, StrategiesLeft } from './strategies';
import { AccountPanel, TodayLeft } from './today';
import { IndexCard } from './ui';

interface Page {
  tab: string;
  pan: number;
  index: ReactNode;
  stageKey: string;
  stage: ReactNode;
  context?: string;
  placeholder: string;
  suggestions: string[];
}

function usePage(): Page {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const param = (pattern: string) => matchPath(pattern, pathname)?.params.id;

  if (pathname.startsWith('/j/strategies')) {
    const id = param('/j/strategies/:id') ?? 'recession-radar';
    const s = strategyById(id) ?? strategyById('recession-radar');
    if (!s) throw new Error('missing strategy');
    return {
      tab: 'Strategies',
      pan: 1,
      index: <StrategiesLeft sel={s.id} />,
      stageKey: `strategy:${s.id}`,
      stage: <BuilderPanel key={s.id} s={s} />,
      context: s.id,
      placeholder: `Ask about ${s.name}, or ask for an edit`,
      suggestions: [`Explain ${s.name}`, 'Suggest a safer edit', 'Draft a trend strategy on QQQ'],
    };
  }
  if (pathname.startsWith('/j/backtests')) {
    const id = param('/j/backtests/:id') ?? BACKTESTS[1].id;
    const b = BACKTESTS.find((x) => x.id === id) ?? BACKTESTS[1];
    return {
      tab: 'Backtests',
      pan: 2,
      index: <BacktestsLeft sel={b.id} />,
      stageKey: `backtest:${b.id}`,
      stage: <BacktestPanel id={b.id} />,
      context: b.strategyId,
      placeholder: 'Ask about this run, or what to test next',
      suggestions: ['Explain this run', 'Suggest a safer edit', 'Draft a trend strategy on QQQ'],
    };
  }
  if (pathname.startsWith('/j/sessions')) {
    const id = param('/j/sessions/:id') ?? 's-rr';
    const s = SESSIONS.find((x) => x.id === id) ?? SESSIONS[1];
    return {
      tab: 'Sessions',
      pan: 3,
      index: <SessionsLeft sel={s.id} />,
      stageKey: `session:${s.id}`,
      stage: <SessionPanel s={s} full />,
      context: s.strategyId,
      placeholder: 'Ask about this session',
      suggestions: ['Why does it hold this?', 'Why is the account down today?'],
    };
  }
  if (pathname.startsWith('/j/portfolio')) {
    const v = params.get('v') ?? 'account';
    return {
      tab: 'Portfolio',
      pan: 4,
      index: <PortfolioLeft sel={v} />,
      stageKey: `portfolio:${v}`,
      stage: v === 'account' ? <AccountPanel eyebrow="Portfolio" /> : <HoldingsPanel cls={v} />,
      placeholder: 'Ask about the account, holdings or risk',
      suggestions: ['Why is the account down today?', "Lower Recession Radar's gold"],
    };
  }
  const sel = params.get('s') ?? 'account';
  const ses = SESSIONS.find((x) => x.id === sel);
  return {
    tab: 'Today',
    pan: 0,
    index: <TodayLeft sel={ses ? ses.id : 'account'} />,
    stageKey: ses ? `session:${ses.id}` : 'account',
    stage: ses ? <SessionPanel s={ses} /> : <AccountPanel />,
    context: ses?.strategyId,
    placeholder: 'Ask about your account, or describe a strategy',
    suggestions: [
      'Why is the account down today?',
      "Lower Recession Radar's gold",
      'Draft a trend strategy on QQQ',
    ],
  };
}

function Frame() {
  const page = usePage();
  const { threadOpen, setThreadOpen } = useAsk();
  const { pathname, search } = useLocation();

  useEffect(() => {
    setThreadOpen(false);
  }, [pathname, search, setThreadOpen]);

  return (
    <Shell
      stageKey={threadOpen ? 'conversation' : page.stageKey}
      stage={threadOpen ? <Conversation back={page.tab} /> : page.stage}
      below={threadOpen ? undefined : <IndexCard>{page.index}</IndexCard>}
      composer={
        <Composer
          key={page.tab}
          context={page.context}
          placeholder={page.placeholder}
          suggestions={page.suggestions}
        />
      }
      pan={page.pan}
    />
  );
}

/** Option J: one card over the chart art, a smaller card under it, and Ask docked under both. */
export default function App() {
  return (
    <AskProvider>
      <Frame />
    </AskProvider>
  );
}
