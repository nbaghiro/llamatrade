/** Where the logo takes a signed-out visitor. "/" renders the marketing page (see App.tsx). */
export const MARKETING_URL = '/';

/** Sign-in for the marketing links. Connecting Alpaca needs an account, so it starts here too. */
export const SIGN_IN_URL = '/login';

/** True in the standalone marketing build (vite.marketing.config.ts), where the app isn't served. */
export const MARKETING_STANDALONE = import.meta.env.VITE_MARKETING_STANDALONE === '1';

/** The app's origin for the standalone build's links; unset hides "Sign in" and "Open app" there. */
export const APP_URL: string | undefined = import.meta.env.VITE_APP_URL;

/**
 * The tape above the nav: each fund with its plain name and a rule the strategy language writes
 * for it. No prices, so nothing goes stale. 'off' removes it.
 */
export const MARKETING_TAPE: 'rules' | 'off' = 'rules';

export interface TapeItem {
  symbol: string;
  name: string;
  rule: string;
}

export const TAPE_ITEMS: readonly TapeItem[] = [
  { symbol: 'SPY', name: 'US large caps', rule: '(sma SPY 200)' },
  { symbol: 'QQQ', name: 'Nasdaq 100', rule: '(momentum QQQ 90)' },
  { symbol: 'VTI', name: 'Total US market', rule: '(asset VTI :weight 40)' },
  { symbol: 'TLT', name: 'Long Treasuries', rule: '(asset TLT :weight 60)' },
  { symbol: 'GLD', name: 'Gold', rule: '(asset GLD :weight 25)' },
  { symbol: 'SMH', name: 'Semiconductors', rule: '(rsi SMH 14)' },
  { symbol: 'XLK', name: 'Tech sector', rule: '(ema XLK 50)' },
  { symbol: 'IWM', name: 'Small caps', rule: '(stddev IWM 20)' },
  { symbol: 'BND', name: 'US bonds', rule: '(asset BND :weight 40)' },
  { symbol: 'VGLT', name: 'Long government bonds', rule: '(momentum VGLT 60)' },
];

/** Loops form id for the invite form; unset or the placeholder means invites are closed here. */
export const LOOPS_FORM_ID: string | undefined = import.meta.env.VITE_LOOPS_FORM_ID;
