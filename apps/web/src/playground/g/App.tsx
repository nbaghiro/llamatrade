import { useEffect, type ReactNode } from 'react';
import { matchPath, useLocation, useSearchParams } from 'react-router-dom';

import { BACKTESTS, SESSIONS, strategyById } from '../data';

import { AskProvider, Composer, Thread } from './ask';
import { useAsk } from './askContext';
import { BacktestPanel, BacktestsLeft } from './backtests';
import { ArtifactPanel } from './copilot';
import { HoldingsPanel, PortfolioLeft } from './portfolio';
import { SessionPanel, SessionsLeft } from './sessions';
import { Shell } from './shell';
import { SignInLeft, SignInStage } from './signin';
import { BuilderPanel, StrategiesLeft } from './strategies';
import { AccountPanel, TodayLeft } from './today';

interface Page {
  tab: string;
  pan: number;
  left: ReactNode;
  stageKey: string;
  stage: ReactNode;
  context?: string;
  placeholder: string;
  suggestions: string[];
  wide?: boolean;
}

function usePage(): Page | 'signin' {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const param = (pattern: string) => matchPath(pattern, pathname)?.params.id;

  if (pathname.startsWith('/g/signin')) return 'signin';

  if (pathname.startsWith('/g/strategies')) {
    const id = param('/g/strategies/:id') ?? 'recession-radar';
    const s = strategyById(id) ?? strategyById('recession-radar');
    if (!s) throw new Error('missing strategy');
    return {
      tab: 'Strategies',
      pan: 1,
      left: <StrategiesLeft sel={s.id} />,
      stageKey: `strategy:${s.id}`,
      stage: <BuilderPanel key={s.id} s={s} />,
      context: s.id,
      placeholder: `Ask about ${s.name}`,
      suggestions: [`Explain ${s.name}`, `Suggest a safer edit`],
      wide: true,
    };
  }
  if (pathname.startsWith('/g/backtests')) {
    const id = param('/g/backtests/:id') ?? BACKTESTS[1].id;
    const b = BACKTESTS.find((x) => x.id === id) ?? BACKTESTS[1];
    return {
      tab: 'Backtests',
      pan: 2,
      left: <BacktestsLeft sel={b.id} />,
      stageKey: `backtest:${b.id}`,
      stage: <BacktestPanel id={b.id} />,
      context: b.strategyId,
      placeholder: 'Ask about a run, or what to test next',
      suggestions: ['Explain this run', 'Draft a trend strategy on QQQ'],
    };
  }
  if (pathname.startsWith('/g/sessions')) {
    const id = param('/g/sessions/:id') ?? 's-rr';
    const s = SESSIONS.find((x) => x.id === id) ?? SESSIONS[1];
    return {
      tab: 'Sessions',
      pan: 3,
      left: <SessionsLeft sel={s.id} />,
      stageKey: `session:${s.id}`,
      stage: <SessionPanel s={s} full />,
      context: s.strategyId,
      placeholder: 'Ask about a session',
      suggestions: ['Why is the account down today?', 'Why does it hold this?'],
    };
  }
  if (pathname.startsWith('/g/portfolio')) {
    const v = params.get('v') ?? 'account';
    return {
      tab: 'Portfolio',
      pan: 4,
      left: <PortfolioLeft sel={v} />,
      stageKey: `portfolio:${v}`,
      stage: v === 'account' ? <AccountPanel eyebrow="Portfolio" /> : <HoldingsPanel cls={v} />,
      placeholder: 'Ask about the account, holdings or risk',
      suggestions: ['Why is the account down today?'],
    };
  }
  const sel = params.get('s') ?? 'account';
  const ses = SESSIONS.find((x) => x.id === sel);
  return {
    tab: 'Today',
    pan: 0,
    left: <TodayLeft sel={ses ? ses.id : 'account'} />,
    stageKey: ses ? `session:${ses.id}` : 'account',
    stage: ses ? <SessionPanel s={ses} /> : <AccountPanel />,
    context: ses?.strategyId,
    placeholder: 'Ask, or describe a strategy',
    suggestions: ['Why is the account down today?', "Lower Recession Radar's gold"],
  };
}

function Frame() {
  const page = usePage();
  const { threadOpen, setThreadOpen, staged, stage } = useAsk();
  const { pathname, search } = useLocation();

  useEffect(() => {
    stage(null);
  }, [pathname, search, stage]);
  useEffect(() => {
    setThreadOpen(false);
  }, [pathname, setThreadOpen]);

  if (page === 'signin')
    return (
      <Shell
        leftKey="signin"
        left={<SignInLeft />}
        stageKey="signin"
        stage={<SignInStage />}
        pan={2}
        nav={false}
        foot={<span>Closed beta · invite only · paper and live trading on Alpaca</span>}
      />
    );

  const showThread = threadOpen;
  return (
    <Shell
      leftKey={showThread ? 'thread' : page.tab}
      left={showThread ? <Thread back={page.tab} /> : page.left}
      composer={
        <Composer
          key={page.tab}
          context={page.context}
          placeholder={page.placeholder}
          suggestions={page.suggestions}
        />
      }
      stageKey={staged ? `ask:${staged.id}` : page.stageKey}
      stage={staged ? <ArtifactPanel turn={staged} /> : page.stage}
      pan={page.pan}
      wide={staged ? staged.artifact !== 'today' : page.wide}
    />
  );
}

/** Option G: every page is the sign-in screen, with the page's essentials and Ask on the left. */
export default function App() {
  return (
    <AskProvider>
      <Frame />
    </AskProvider>
  );
}
