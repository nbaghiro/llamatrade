import { MessageRole } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useState, type FormEvent } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { CopilotMark } from '../../common/Logo';

/** Ask Copilot about this draft. A proposed change comes back as a tracked edit in the outline. */
export function CopilotAsk() {
  const getDSLCode = useStrategyBuilderStoreWithContext((s) => s.getDSLCode);
  const name = useStrategyBuilderStoreWithContext((s) => s.strategyName);
  const sendMessage = useAgentStore((s) => s.sendMessage);
  const isStreaming = useAgentStore((s) => s.isStreaming);
  const messages = useAgentStore((s) => s.messages);
  const [text, setText] = useState('');

  const lastAsked = [...messages].reverse().find((m) => m.role === MessageRole.USER)?.content;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (!q || isStreaming) return;
    setText('');
    sendMessage(q, getDSLCode(), name, 'strategy-builder').catch(() => undefined);
  };

  return (
    <form onSubmit={submit} className="mb-4 grid gap-1.5">
      <label className="flex h-10 items-center gap-2 rounded-[6px] border border-line-strong bg-panel px-3 focus-within:border-accent">
        <CopilotMark className="h-4 w-4 text-fg-3" />
        <span className="sr-only">Ask Copilot about this strategy</span>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={lastAsked ?? 'Ask Copilot about this strategy'}
          className="min-w-0 flex-1 bg-transparent text-[13px] text-fg outline-none placeholder:text-fg-3"
        />
        {isStreaming ? (
          <span className="text-[11.5px] text-fg-3">Copilot is working</span>
        ) : (
          text.trim() && (
            <button type="submit" className="btn btn-primary btn-sm">
              Ask
            </button>
          )
        )}
      </label>
    </form>
  );
}
