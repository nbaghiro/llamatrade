import { NotificationCategory as C } from '@llamatrade/core/proto/events_pb';

export interface EmailPreview {
  subject: string;
  body: string;
}

/** Made-up example values for the fields a real notice fills in; the preview says so. */
const SYM = 'TLT';
const REASON = '{reason}';
const AMT = ' ($3,797.22)';

/** An example reason that fits each kind of notice; anything unlisted was stopped by you. */
const SAMPLE_REASON: Partial<Record<C, string>> = {
  [C.SLEEVE_FROZEN]: 'Alpaca and the ledger disagree on TLT',
  [C.FILL_QUARANTINED]: 'the fill matched no open order',
  [C.ORDER_REJECTED]: 'insufficient buying power',
  [C.RISK_BREACH]: 'it would exceed the position limit',
  [C.POSITION_DRIFT]: 'the share counts differ',
  [C.RECONCILIATION_DRIFT]: 'the share counts differ',
  [C.EVALUATION_STALLED]: 'no new prices for 10 minutes',
  [C.SYMBOL_NOT_TRADABLE]: 'trading is halted',
  [C.CONNECTION_LOST]: 'the price feed disconnected',
  [C.STRATEGY_ERROR]: 'a rule referred to a missing price',
  [C.SESSION_ERROR]: 'Alpaca rejected the keys',
  [C.CIRCUIT_BREAKER_TRIGGERED]: 'the daily loss limit was reached',
  [C.FUNDING_FAILED]: 'not enough free cash',
  [C.PLAN_LIMIT_REACHED]: 'backtests this month',
  [C.BACKTEST_FAILED]: 'no prices for TLT before 2002',
  [C.SUBSCRIPTION_UPDATED]: 'moved to the monthly plan',
  [C.PRICE_ALERT_TRIGGERED]: 'it crossed $90.00',
  [C.WEBHOOK_DISABLED]: 'ten failed deliveries in a row',
  [C.EXECUTION_CANCELLED]: 'you cancelled it',
};

/**
 * The email each kind of notice sends, mirroring services/notification/src/templates.py,
 * with example values where the real notice fills in its own.
 */
const TEMPLATES: Partial<Record<C, [string, string]>> = {
  [C.SLEEVE_FROZEN]: [
    'Sleeve frozen',
    `A sleeve on your account was frozen${REASON}. New orders on it are rejected until the discrepancy is resolved.`,
  ],
  [C.FILL_QUARANTINED]: [
    'Fill quarantined',
    `A fill could not be booked${REASON}. It is parked for operator review and your ledger is unchanged.`,
  ],
  [C.EXTERNAL_TRADE_ADOPTED]: [
    'External trade detected',
    `A holding ${SYM} not placed by LlamaTrade was found at your broker and was adopted into your Unmanaged sleeve.`,
  ],
  [C.CORPORATE_ACTION_PROPOSED]: [
    'Corporate action pending',
    `A corporate action ${SYM}${AMT} was detected and awaits review before it is applied to your ledger.`,
  ],
  [C.CORPORATE_ACTION_APPLIED]: [
    'Corporate action applied',
    `A corporate action ${SYM}${AMT} was applied to your ledger.`,
  ],
  [C.ORDER_FILLED]: ['Order filled', `Your order ${SYM}${AMT} filled.`],
  [C.ORDER_REJECTED]: ['Order rejected', `Your order ${SYM} was rejected${REASON}`],
  [C.POSITION_OPENED]: ['Position opened', `A position ${SYM}${AMT} was opened.`],
  [C.POSITION_CLOSED]: ['Position closed', `A position ${SYM}${AMT} was closed.`],
  [C.POSITION_DRIFT]: [
    'Position drift',
    `Your broker and LlamaTrade disagree on a position ${SYM}${REASON}`,
  ],
  [C.RISK_BREACH]: ['Order blocked by risk gate', `An order ${SYM} was blocked${REASON}`],
  [C.EVALUATION_STALLED]: [
    'Strategy evaluation stalled',
    `A live strategy has not evaluated recently${REASON}. Positions are unchanged while the gate is closed.`,
  ],
  [C.SYMBOL_NOT_TRADABLE]: [
    'Symbol not tradable',
    `A symbol ${SYM} in a live strategy is halted or delisted${REASON}. A decision is needed on the affected position.`,
  ],
  [C.CONNECTION_LOST]: ['Broker connection lost', `A live data connection dropped${REASON}`],
  [C.STRATEGY_ERROR]: ['Strategy error', `A live strategy hit an error${REASON}`],
  [C.SESSION_STARTED]: ['Trading session started', 'A live trading session started.'],
  [C.SESSION_STOPPED]: ['Trading session stopped', `A live trading session stopped${REASON}`],
  [C.SESSION_ERROR]: ['Trading session failed', `A live trading session failed${REASON}`],
  [C.CIRCUIT_BREAKER_TRIGGERED]: [
    'Circuit breaker triggered',
    `Trading was halted by a circuit breaker${REASON}`,
  ],
  [C.CIRCUIT_BREAKER_RESET]: [
    'Circuit breaker reset',
    'Trading resumed after a circuit-breaker halt.',
  ],
  [C.STOP_LOSS_HIT]: ['Stop loss hit', `A stop loss ${SYM}${AMT} executed.`],
  [C.TAKE_PROFIT_HIT]: ['Take profit hit', `A take profit ${SYM}${AMT} executed.`],
  [C.RECONCILIATION_DRIFT]: [
    'Reconciliation drift',
    `Reconciliation found a discrepancy ${SYM}${REASON}`,
  ],
  [C.EXECUTION_STARTED]: ['Session started', 'Your strategy is funded and running.'],
  [C.EXECUTION_STOPPED]: ['Strategy stopped', `Your strategy stopped${REASON}`],
  [C.FUNDING_FAILED]: [
    'Start failed at funding',
    `Your strategy could not be funded and did not go live${REASON}`,
  ],
  [C.SLEEVE_RELEASE_DEFERRED]: [
    'Capital release delayed',
    "Your stopped strategy's capital could not be released yet. A background sweep keeps retrying; no action is needed, but we are flagging it.",
  ],
  [C.EXECUTION_CANCELLED]: ['Execution cancelled', `A pending execution was cancelled${REASON}`],
  [C.PLAN_LIMIT_REACHED]: [
    'Plan limit reached',
    `You hit a plan limit${REASON}. Upgrade to raise it.`,
  ],
  [C.BACKTEST_COMPLETED]: ['Backtest completed', 'Your backtest finished and results are ready.'],
  [C.BACKTEST_FAILED]: ['Backtest failed', `Your backtest did not complete${REASON}`],
  [C.PAYMENT_SUCCEEDED]: [
    'Payment received',
    `Your subscription payment${AMT} was received. Thank you.`,
  ],
  [C.PAYMENT_FAILED]: [
    'Payment failed',
    'Your subscription payment failed. Update your payment method to avoid losing the ability to start live strategies.',
  ],
  [C.TRIAL_ENDING]: [
    'Trial ending soon',
    "Your trial ends soon. Add a payment method to keep your plan's features.",
  ],
  [C.SUBSCRIPTION_UPDATED]: ['Subscription updated', `Your subscription changed${REASON}`],
  [C.SUBSCRIPTION_CANCELED]: [
    'Subscription canceled',
    'Your subscription was canceled. Running strategies keep trading; new live sessions can’t be started.',
  ],
  [C.CONFIRMATION_PENDING]: [
    'Copilot action awaiting approval',
    'A copilot proposal is waiting for your confirmation.',
  ],
  [C.PRICE_ALERT_TRIGGERED]: ['Price alert triggered', `Your alert ${SYM} triggered${REASON}`],
  [C.WEBHOOK_DISABLED]: [
    'Webhook disabled',
    `A webhook endpoint kept failing and was disabled${REASON}. Re-enable it from Settings once fixed.`,
  ],
};

export function emailPreview(category: C): EmailPreview {
  const [title, body] = TEMPLATES[category] ?? ['Notification', 'You have a new notification.'];
  const reason = SAMPLE_REASON[category] ?? 'you stopped it';
  return { subject: `LlamaTrade: ${title}`, body: body.replace(REASON, `: ${reason}`) };
}
