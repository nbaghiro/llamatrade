/** Session state derivation and order outcome helpers for the sessions console. */

import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { OrderStatus } from '@llamatrade/core/proto/trading_pb';

import type { RunState } from '../components/ui/StatusMark';

import { tradingDayOnOrAfter } from './marketHolidays';

export type SessionState = 'running' | 'starting' | 'paused' | 'frozen' | 'stopped' | 'error';

export interface SessionStateInput {
  /** TradingSession.is_active: true only while the session row is running. */
  isActive: boolean;
  /** TradingSession.ended_at is set: the session was stopped. */
  ended?: boolean;
  executionStatus?: ExecutionStatus;
  sleeveStatus?: SleeveStatus;
}

/**
 * One state per session. A frozen sleeve outranks running and paused because new orders
 * wait on it. A session that is neither active nor ended is paused, unless its execution
 * hasn't started yet.
 */
export function deriveSessionState({
  isActive,
  ended = false,
  executionStatus = ExecutionStatus.UNSPECIFIED,
  sleeveStatus = SleeveStatus.UNSPECIFIED,
}: SessionStateInput): SessionState {
  if (executionStatus === ExecutionStatus.ERROR) return 'error';
  if (
    ended ||
    executionStatus === ExecutionStatus.STOPPED ||
    sleeveStatus === SleeveStatus.CLOSED
  ) {
    return 'stopped';
  }
  if (sleeveStatus === SleeveStatus.FROZEN) return 'frozen';
  if (executionStatus === ExecutionStatus.PAUSED) return 'paused';
  if (isActive) return 'running';
  if (executionStatus === ExecutionStatus.PENDING) return 'starting';
  return 'paused';
}

export type SessionAction = 'pause' | 'resume' | 'stop';

export interface SessionStateView {
  mark: RunState;
  label: string;
  /** Generic reason copy; the API carries no per-session reason. */
  reason: string;
  actions: readonly SessionAction[];
  /** Raised in amber above the console. */
  attention: boolean;
  /** Still holds or may hold a sleeve, so it counts as open. */
  open: boolean;
}

const VIEW: Record<SessionState, SessionStateView> = {
  running: {
    mark: 'running',
    label: 'Running',
    reason: 'Streaming bars and ready to rebalance on schedule.',
    actions: ['pause', 'stop'],
    attention: false,
    open: true,
  },
  starting: {
    mark: 'waiting',
    label: 'Starting',
    reason: 'The session is set up and starts with the next market data.',
    actions: ['stop'],
    attention: false,
    open: true,
  },
  paused: {
    mark: 'paused',
    label: 'Paused',
    reason: 'Evaluation is suspended. Holdings stay as they are until you resume.',
    actions: ['resume', 'stop'],
    attention: false,
    open: true,
  },
  frozen: {
    mark: 'frozen',
    label: 'Frozen',
    reason:
      "The ledger and Alpaca disagree about this session's holdings. New orders wait until the difference is resolved.",
    actions: ['stop'],
    attention: true,
    open: true,
  },
  stopped: {
    mark: 'stopped',
    label: 'Stopped',
    reason: 'This session has stopped and places no new orders.',
    actions: [],
    attention: false,
    open: false,
  },
  error: {
    mark: 'error',
    label: 'Stopped by an error',
    reason: 'The session stopped because of an error and places no new orders.',
    actions: [],
    attention: true,
    open: false,
  },
};

export function sessionStateView(state: SessionState): SessionStateView {
  return VIEW[state];
}

/** Open first, attention before calm, then newest first. */
export function sessionSortKey(state: SessionState): number {
  const order: SessionState[] = ['frozen', 'error', 'running', 'starting', 'paused', 'stopped'];
  return order.indexOf(state);
}

export type OrderOutcome = 'filled' | 'partial' | 'open' | 'stopped' | 'rejected' | 'closed';

const OPEN_STATUSES = new Set([OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.ACCEPTED]);

/**
 * A rejected order that never reached the broker was stopped before sending (a risk check);
 * one rejected after submission was refused by the broker.
 */
export function orderOutcome(status: OrderStatus, submitted: boolean): OrderOutcome {
  if (status === OrderStatus.FILLED) return 'filled';
  if (status === OrderStatus.PARTIAL) return 'partial';
  if (OPEN_STATUSES.has(status)) return 'open';
  if (status === OrderStatus.REJECTED) return submitted ? 'rejected' : 'stopped';
  return 'closed';
}

export const ORDER_OUTCOME_LABEL: Record<OrderOutcome, string> = {
  filled: 'Filled',
  partial: 'Partly filled',
  open: 'Open',
  stopped: 'Not sent',
  rejected: 'Rejected by Alpaca',
  closed: 'Closed',
};

/** The seven checks every order runs through before it reaches Alpaca, in order. */
export const RISK_CHECKS: readonly string[] = [
  'Market is open',
  'Order value',
  'Sleeve is active and has the cash',
  'Symbol is allowed',
  'Position size after the order',
  'Daily loss',
  'Order rate',
];

const CHECK_PATTERNS: readonly [number, RegExp][] = [
  [0, /market is closed/i],
  [2, /sleeve|free cash|buying power|holdings/i],
  [1, /order value|verify order value/i],
  [3, /not in allowed list/i],
  [4, /position would exceed/i],
  [5, /daily loss/i],
  [6, /rate limit/i],
];

/** Indexes into RISK_CHECKS named by a rejection message, in check order. */
export function stoppingChecks(message: string): number[] {
  const found = new Set<number>();
  for (const part of message.split(/;|\n/)) {
    for (const [i, re] of CHECK_PATTERNS) {
      if (re.test(part)) {
        found.add(i);
        break;
      }
    }
  }
  return [...found].sort((a, b) => a - b);
}

/** Default limits from the trading service, used when an account has none of its own. */
export const DEFAULT_RISK_LIMITS = {
  maxOrderValue: 5000,
  maxPositionSize: 10000,
  maxDailyLoss: 1000,
  ordersPerMinute: 10,
} as const;

export interface SessionFiguresInput {
  /** Sleeve value now, from the portfolio service. */
  currentValue: number | null;
  allocated: number | null;
  /** One-day return as a fraction. */
  return1d: number | null;
  cash: number | null;
}

export interface SessionFigures {
  equity: number | null;
  today: number | null;
  todayPct: number | null;
  total: number | null;
  totalPct: number | null;
  cashShare: number | null;
}

const known = (v: number | null): v is number => v !== null && Number.isFinite(v);

/** The four session figures; each stays null when its inputs are missing. */
export function sessionFigures({
  currentValue,
  allocated,
  return1d,
  cash,
}: SessionFiguresInput): SessionFigures {
  const equity = known(currentValue) ? currentValue : null;
  const today =
    equity !== null && known(return1d) && return1d > -1 ? equity - equity / (1 + return1d) : null;
  const total = equity !== null && known(allocated) && allocated > 0 ? equity - allocated : null;
  return {
    equity,
    today,
    todayPct: today === null ? null : (return1d as number),
    total,
    totalPct: total === null ? null : total / (allocated as number),
    cashShare: known(cash) && equity !== null && equity > 0 ? cash / equity : null,
  };
}

const FIRST_OF_PERIOD: Record<string, number> = { monthly: 1, quarterly: 3, annually: 12 };

/**
 * The next scheduled rebalance for a running session: the first trading day of the next
 * week, month, quarter or year (the runtime rebalances on the first bar of a new period).
 * `today` is the calendar date in New York at UTC midnight. Daily and unknown schedules
 * return null. Weekends and NYSE holidays are skipped.
 */
export function nextRebalanceDate(rebalance: string | undefined, today: Date): Date | null {
  const freq = (rebalance ?? '').trim().toLowerCase();
  const y = today.getUTCFullYear();
  const m = today.getUTCMonth();
  if (freq === 'weekly') {
    const daysToMonday = (8 - today.getUTCDay()) % 7 || 7;
    return tradingDayOnOrAfter(new Date(Date.UTC(y, m, today.getUTCDate() + daysToMonday)));
  }
  const step = FIRST_OF_PERIOD[freq];
  if (!step) return null;
  const nextMonth = (Math.floor(m / step) + 1) * step;
  return tradingDayOnOrAfter(new Date(Date.UTC(y, nextMonth, 1)));
}
