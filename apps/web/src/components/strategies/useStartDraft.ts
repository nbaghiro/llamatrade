import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useUIStore } from '../../store/ui';

/** Every way into a new strategy lands in the editor as an unsaved draft. */
export function useStartDraft() {
  const navigate = useNavigate();
  const close = useUIStore((s) => s.closeAllStrategyDialogs);
  const startNewChat = useAgentStore((s) => s.startNewChat);
  const sendMessage = useAgentStore((s) => s.sendMessage);

  const fromTemplate = useCallback(
    (t: Pick<StrategyTemplate, 'id'>) => {
      close();
      navigate(`/strategies/builder?template=${encodeURIComponent(t.id)}`);
    },
    [close, navigate]
  );

  const blank = useCallback(
    (mode: 'tree' | 'code') => {
      close();
      navigate(mode === 'code' ? '/strategies/builder?mode=code' : '/strategies/builder');
    },
    [close, navigate]
  );

  /** Opens a blank draft and asks Copilot to write it; the proposal arrives as a tracked change. */
  const describe = useCallback(
    (text: string) => {
      startNewChat();
      close();
      navigate('/strategies/builder');
      sendMessage(text, '', '', 'new-strategy').catch(() => undefined);
    },
    [close, navigate, startNewChat, sendMessage]
  );

  return { fromTemplate, blank, describe };
}
