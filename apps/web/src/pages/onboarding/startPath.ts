import type { PathStep } from '../../components/auth/accountPaths';

/** Backtest, paper session, live session, with the broker marked as connected or not (start2 A). */
export function startPath(paperConnected: boolean): PathStep[] {
  return [
    { title: 'Backtest', sub: 'Any of the three ways above.' },
    {
      title: 'Paper session',
      sub: paperConnected ? 'Alpaca paper is connected.' : 'Needs Alpaca paper. Not connected yet.',
    },
    {
      title: 'Live session',
      sub: 'A separate Alpaca connection, when you choose. Needs a paid plan, live keys and a margin account with $500 of buying power.',
    },
  ];
}
