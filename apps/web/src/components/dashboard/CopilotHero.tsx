import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAgentStore } from '../../store/agent';
import { useDashboardStore } from '../../store/dashboard';

const DEFAULT_PROMPTS = [
  'Build a momentum rotation',
  'How is my portfolio doing?',
  'Backtest my last idea',
];

export default function CopilotHero() {
  const [draft, setDraft] = useState('');
  const navigate = useNavigate();
  const openChat = useAgentStore((s) => s.openChat);
  const sendMessage = useAgentStore((s) => s.sendMessage);
  const getSuggestedPrompts = useAgentStore((s) => s.getSuggestedPrompts);
  const suggestedPrompts = useAgentStore((s) => s.suggestedPrompts);
  const liveStrategiesCount = useDashboardStore((s) => s.liveStrategiesCount);

  useEffect(() => {
    getSuggestedPrompts({ page: 'dashboard' });
  }, [getSuggestedPrompts]);

  const prompts = (suggestedPrompts.length > 0 ? suggestedPrompts : DEFAULT_PROMPTS).slice(0, 3);

  // Route to the full-page Copilot; when seeded with a prompt, open fresh then send it.
  const launch = (prompt?: string) => {
    openChat();
    if (prompt) {
      sendMessage(prompt, undefined, undefined, 'dashboard');
    }
    navigate('/copilot');
  };

  const submitDraft = () => {
    const text = draft.trim();
    launch(text || undefined);
    setDraft('');
  };

  return (
    <div className="bg-ink text-bone border-2 border-ink shadow-[4px_4px_0_#ff4d1c] flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-bone/20">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">✦ Copilot</span>
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-bone/30 px-1.5 py-0.5">
          DSL
        </span>
      </div>

      <div className="p-4 flex flex-col flex-1">
        <div className="font-display uppercase text-[26px] leading-[0.98] tracking-[0.01em]">
          Describe a
          <br />
          strategy.
          <br />
          <span className="text-orange-500">Ship it live.</span>
        </div>

        <div className="mt-4 flex items-center border-2 border-orange-500 bg-bone/[0.04] px-3 py-3">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitDraft()}
            placeholder="Buy tech when RSI < 30, hedge bonds…"
            className="flex-1 bg-transparent outline-none font-mono text-xs text-bone placeholder:text-bone/55"
            aria-label="Describe a strategy for the Copilot"
          />
          <button
            onClick={submitDraft}
            aria-label="Send to Copilot"
            className="ml-2 font-mono text-orange-500 text-sm font-bold"
          >
            →
          </button>
        </div>

        <div className="flex flex-col gap-2 mt-3.5">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              onClick={() => launch(prompt)}
              className="flex items-center gap-2.5 border-[1.5px] border-bone/30 px-3 py-2.5 text-left font-mono text-[10.5px] font-bold uppercase tracking-[0.03em] text-bone/85 hover:border-orange-500 transition-colors"
            >
              <span className="flex-1">{prompt}</span>
              <span className="text-orange-500">→</span>
            </button>
          ))}
        </div>

        <div className="mt-auto pt-3.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-bone/40">
          {liveStrategiesCount > 0
            ? `Grounded in your ${liveStrategiesCount} live ${liveStrategiesCount === 1 ? 'strategy' : 'strategies'}`
            : 'Grounded in your account'}
        </div>
      </div>
    </div>
  );
}
