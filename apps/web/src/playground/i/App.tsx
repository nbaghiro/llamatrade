import { useEffect, type ReactNode } from 'react';
import { matchPath, useLocation, useSearchParams } from 'react-router-dom';

import { BACKTESTS, SESSIONS, strategyById } from '../data';

import { AskProvider, AskRow, Conversation } from './ask';
import { useAsk } from './askContext';
import { BacktestPanel, BacktestsList } from './backtests';
import { HoldingsPanel, PortfolioList } from './portfolio';
import { SessionPanel, SessionsList } from './sessions';
import { Shell } from './shell';
import { BuilderPanel, StrategiesList } from './strategies';
import { AccountPanel, TodayBelow } from './today';

interface Page {
  tab: string;
  pan: number;
  key: string;
  body: ReactNode;
  below: ReactNode;
  context?: string;
  placeholder: string;
  suggestions: string[];
}

function usePage(): Page {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const param = (pattern: string) => matchPath(pattern, pathname)?.params.id;

  if (pathname.startsWith('/i/strategies')) {
    const id = param('/i/strategies/:id') ?? 'recession-radar';
    const s = strategyById(id) ?? strategyById('recession-radar');
    if (!s) throw new Error('missing strategy');
    return {
      tab: 'Strategies',
      pan: 1,
      key: `strategy:${s.id}`,
      body: <BuilderPanel key={s.id} s={s} />,
      below: <StrategiesList sel={s.id} />,
      context: s.id,
      placeholder: `Ask about ${s.name}, or describe a change`,
      suggestions: [`Explain ${s.name}`, 'Suggest a safer edit'],
    };
  }
  if (pathname.startsWith('/i/backtests')) {
    const id = param('/i/backtests/:id') ?? BACKTESTS[1].id;
    const b = BACKTESTS.find((x) => x.id === id) ?? BACKTESTS[1];
    return {
      tab: 'Backtests',
      pan: 2,
      key: `backtest:${b.id}`,
      body: <BacktestPanel id={b.id} />,
      below: <BacktestsList sel={b.id} />,
      context: b.strategyId,
      placeholder: 'Ask about this run, or what to test next',
      suggestions: ['Explain this run', 'Draft a trend strategy on QQQ'],
    };
  }
  if (pathname.startsWith('/i/sessions')) {
    const id = param('/i/sessions/:id') ?? 's-rr';
    const s = SESSIONS.find((x) => x.id === id) ?? SESSIONS[1];
    return {
      tab: 'Sessions',
      pan: 3,
      key: `session:${s.id}`,
      body: <SessionPanel key={s.id} s={s} full />,
      below: <SessionsList sel={s.id} />,
      context: s.strategyId,
      placeholder: 'Ask about this session',
      suggestions: ['Why does it hold this?', 'Why is the account down today?'],
    };
  }
  if (pathname.startsWith('/i/portfolio')) {
    const v = params.get('v') ?? 'all';
    return {
      tab: 'Portfolio',
      pan: 4,
      key: `portfolio:${v}`,
      body: v === 'account' ? <AccountPanel /> : <HoldingsPanel cls={v} />,
      below: <PortfolioList sel={v} />,
      placeholder: 'Ask about the account, holdings or risk',
      suggestions: ['Why is the account down today?'],
    };
  }
  return {
    tab: 'Today',
    pan: 0,
    key: 'today',
    body: <AccountPanel greet />,
    below: <TodayBelow />,
    placeholder: 'Ask about your account, or describe a strategy',
    suggestions: ['Why is the account down today?', "Lower Recession Radar's gold"],
  };
}

function Frame() {
  const page = usePage();
  const { open, setOpen } = useAsk();
  const { pathname, search } = useLocation();
  useEffect(() => {
    setOpen(false);
  }, [pathname, search, setOpen]);

  return (
    <Shell
      pan={page.pan}
      ask={
        <AskRow
          key={page.tab}
          back={page.tab}
          context={page.context}
          placeholder={page.placeholder}
          suggestions={page.suggestions}
        />
      }
      bodyKey={open ? 'conversation' : page.key}
      body={open ? <Conversation /> : page.body}
      below={open ? undefined : page.below}
    />
  );
}

/** Option I: one card over the art per page, with the Ask line as the card's first row. */
export default function App() {
  return (
    <AskProvider>
      <Frame />
    </AskProvider>
  );
}
