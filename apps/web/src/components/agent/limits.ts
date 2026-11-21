/** Why Copilot can't take a message right now (limits A). */
export type CopilotLimit = 'outage' | 'rate';

/** The agent service answers RESOURCE_EXHAUSTED when an account sends too many messages a minute. */
export function isRateLimited(error: string | null | undefined): boolean {
  return !!error && /resource[_ ]exhausted|too many requests/i.test(error);
}

export function copilotLimit(state: {
  serviceUnavailable: boolean;
  error: string | null;
}): CopilotLimit | null {
  if (state.serviceUnavailable) return 'outage';
  if (isRateLimited(state.error)) return 'rate';
  return null;
}

const ET_TIME = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/New_York',
});

export interface LimitCopy {
  title: string;
  body: string;
}

/** What the notice in the composer's place says, given when it started and whether a question was kept. */
export function limitCopy(limit: CopilotLimit, since: Date | null, kept: boolean): LimitCopy {
  if (limit === 'rate') {
    return {
      title: 'Too many questions in the last minute',
      body: kept
        ? 'Copilot can answer again in about a minute. Your question is kept and won’t be sent until you try again.'
        : 'Copilot can answer again in about a minute. Until then you can read every conversation and use the rest of the app as usual.',
    };
  }
  const when = since ? `Since ${ET_TIME.format(since)} ET. ` : '';
  return {
    title: 'Copilot can’t reach its model',
    body: kept
      ? `${when}Your question is kept and won’t be sent until you try again. Sessions, orders and backtests aren’t affected.`
      : `${when}You can read every conversation, open drafts in the builder, run backtests yourself and use sessions as usual.`,
  };
}
