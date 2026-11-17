import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useCallback } from 'react';

import { subjectContext, useCopilotSubject } from './subjectStore';

/**
 * Sends a message with the chosen subject's strategy as context. When Copilot can't be reached
 * the question is kept as an unsent draft instead of being lost.
 */
export function useCopilotSend(page: string) {
  const sendMessage = useAgentStore((s) => s.sendMessage);
  return useCallback(
    async (content: string) => {
      const { subject, setUnsent } = useCopilotSubject.getState();
      const ctx = subjectContext(subject);
      setUnsent(null);
      await sendMessage(content, ctx.dsl, ctx.name, page);
      if (useAgentStore.getState().serviceUnavailable) setUnsent(content);
    },
    [sendMessage, page]
  );
}
