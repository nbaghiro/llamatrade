import { MessageRole, type AgentMessage } from '@llamatrade/core/stores/agent';

import { stripDraftInstruction } from './draftQuestions';
import { subjectQuestions, type CopilotSubject } from './subjects';

/** The questions about this subject that haven't been asked yet in the thread. */
export function followUpsFor(
  subject: CopilotSubject | null,
  messages: readonly AgentMessage[],
  limit = 2
): string[] {
  if (!subject) return [];
  const asked = new Set(
    messages
      .filter((m) => m.role === MessageRole.USER)
      .map((m) => stripDraftInstruction(m.content).trim().toLowerCase())
  );
  return subjectQuestions(subject)
    .map((q) => q.text)
    .filter((q) => !asked.has(q.toLowerCase()))
    .slice(0, limit);
}
