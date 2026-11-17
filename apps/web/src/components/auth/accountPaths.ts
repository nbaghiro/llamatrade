export interface PathStep {
  title: string;
  sub: string;
}

/** The three steps every account goes through, used on Create account. */
export const SIGNUP_PATH: readonly PathStep[] = [
  { title: 'Backtest', sub: 'Right after this. No broker needed.' },
  { title: 'Paper', sub: 'Connect Alpaca paper. Simulated money.' },
  { title: 'Live', sub: 'A separate connection, when you choose.' },
];

/** What going live needs, said the same way wherever the app explains it. */
export const LIVE_REQUIREMENTS =
  'Going live needs an active or trialing paid plan, live Alpaca keys, and an active Alpaca margin account with at least $500 of buying power.';
