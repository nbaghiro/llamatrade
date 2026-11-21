import { MessageRole, useAgentStore } from '@llamatrade/core/stores/agent';
import { useCallback } from 'react';

import { draftRequest, looksLikeDraft } from './draftQuestions';
import { copilotLimit } from './limits';
import { subjectContext, useCopilotSubject } from './subjectStore';

/** Drops the optimistic copy of a message that never reached Copilot, so a retry isn't doubled. */
function dropFailed(content: string) {
  const { messages } = useAgentStore.getState();
  const last = messages[messages.length - 1];
  if (
    last &&
    last.role === MessageRole.USER &&
    last.id.startsWith('temp-') &&
    last.content === content
  ) {
    useAgentStore.setState({ messages: messages.slice(0, -1) });
  }
}

/**
 * Sends a message with the chosen subject's strategy as context. On the Copilot page a strategy
 * description goes out as a draft request, so Copilot asks its questions first (draft2 B). When
 * Copilot can't take the message, it is kept as an unsent question instead of being lost.
 */
export function useCopilotSend(page: string) {
  const sendMessage = useAgentStore((s) => s.sendMessage);
  return useCallback(
    async (content: string, options: { draft?: boolean; retry?: boolean } = {}) => {
      const { subject, unsent, setUnsent } = useCopilotSubject.getState();
      if (options.retry && unsent) dropFailed(unsent.text);
      const ctx = subjectContext(subject);
      const draft =
        !options.retry && (options.draft ?? (page === 'copilot' && looksLikeDraft(content)));
      const text = draft ? draftRequest(content) : content;
      setUnsent(null);
      useAgentStore.setState({ error: null });
      await sendMessage(text, ctx.dsl, ctx.name, page);
      if (copilotLimit(useAgentStore.getState())) setUnsent(text);
    },
    [sendMessage, page]
  );
}
