/** The request sent with the description, so Copilot asks before it writes (draft2 B). */
export function questionsFirstPrompt(description: string): string {
  return [
    description,
    '',
    'Before you write a draft, ask me about the parts of this that could mean more than one rule, such as which symbols, what threshold or how to split the money. Keep it to three short questions at most, each with the options you would consider and the one you would pick. If nothing is unclear, write the draft straight away.',
  ].join('\n');
}

export const SKIP_PROMPT =
  'Skip the remaining questions and write the draft now, using the option you would pick for each.';
