/** Home is the Copilot chat; a conversation keeps its own address under /copilot. */
export const CHAT_HOME = '/dashboard';
export const HISTORY_PATH = `${CHAT_HOME}?view=history`;

export function conversationPath(id: string): string {
  return `/copilot/${id}`;
}

/**
 * The link that opens Copilot about one subject with a question ("session:<id>",
 * "strategy:<id>", "backtest:<id>", "account"). With `send`, the page asks it at once;
 * otherwise it waits in the composer to be finished.
 */
export function askCopilotHref(
  question: string,
  about?: string,
  options: { send?: boolean } = {}
): string {
  const params = new URLSearchParams();
  if (about) params.set('about', about);
  const q = question.trim();
  if (q) params.set('q', q);
  if (q && options.send) params.set('send', '1');
  const qs = params.toString();
  return qs ? `${CHAT_HOME}?${qs}` : CHAT_HOME;
}
