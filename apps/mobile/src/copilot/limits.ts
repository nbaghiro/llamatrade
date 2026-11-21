/** Why Copilot can't take a message right now (limits B). */
export type CopilotLimit = 'outage' | 'rate';

/** The agent service answers RESOURCE_EXHAUSTED past 30 messages a minute per account. */
export function isRateLimited(error: string | null | undefined): boolean {
  return !!error && /resource[_ ]exhausted|too many requests|rate limit/i.test(error);
}

export function copilotLimit(state: { serviceUnavailable: boolean; error: string | null }): CopilotLimit | null {
  if (state.serviceUnavailable) return 'outage';
  if (isRateLimited(state.error)) return 'rate';
  return null;
}

export interface LimitCopy {
  title: string;
  body: string;
}

function clock(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** The notice in the composer's place: what happened, when it can answer, and whether a question was kept. */
export function limitCopy(limit: CopilotLimit, since: Date | null, kept: boolean): LimitCopy {
  if (limit === 'rate') {
    return {
      title: 'Too many questions in the last minute',
      body: kept
        ? 'Copilot can answer again in about a minute. Your question is kept and won’t be sent until you try again.'
        : 'Copilot can answer again in about a minute. Your conversations and the rest of the app work as usual.',
    };
  }
  const when = since ? `Since ${clock(since)}. ` : '';
  return {
    title: 'Copilot can’t reach its model',
    body: kept
      ? `${when}Your question is kept and won’t be sent until you try again. Sessions, orders and backtests aren’t affected.`
      : `${when}Your conversations are still here, and sessions, orders and backtests aren’t affected.`,
  };
}
