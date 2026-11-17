/**
 * The link that opens Copilot about one subject with a question in the composer, for asking
 * from a marker card or any page ("session:<id>", "strategy:<id>", "backtest:<id>", "account").
 */
export function askCopilotHref(question: string, about?: string): string {
  const params = new URLSearchParams();
  if (about) params.set('about', about);
  if (question.trim()) params.set('q', question.trim());
  const qs = params.toString();
  return qs ? `/copilot?${qs}` : '/copilot';
}
