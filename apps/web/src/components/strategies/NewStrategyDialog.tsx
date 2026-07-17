/**
 * New Strategy — Copilot command bar + the shared template catalog.
 *
 * Three grounded paths that never compete:
 *  1. Copilot command bar (header) — describe a strategy; hands off to the
 *     embedded full Copilot conversation.
 *  2. Template catalog (TemplateBrowser) — filter/search, live preview, and
 *     "Use this template" / "Customize with Copilot".
 *  3. Start from scratch — the blocks/DSL builder.
 */

import { useAgentStore } from '@llamatrade/core/stores/agent';
import { ArrowLeft, ArrowRight, Maximize2, Sparkles, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { CopilotConversation } from '../../components/agent/CopilotConversation';
import type { StrategyTemplate } from '../../data/strategy-templates';
import { useStrategyBuilderStore } from '../../store/strategy-builder';
import { MagicIcon } from '../common/MagicIcon';

import { TemplateBrowser } from './TemplateBrowser';

const EXAMPLE_PROMPTS: readonly string[] = [
  '60/40 with a 10% gold sleeve',
  'RSI mean-reversion on QQQ',
  'Dividend growth, low turnover',
  'Dual momentum, stocks vs. bonds',
];

interface NewStrategyDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function NewStrategyDialog({ isOpen, onClose }: NewStrategyDialogProps) {
  const navigate = useNavigate();
  const { createNew } = useStrategyBuilderStore();
  const startNewChat = useAgentStore((s) => s.startNewChat);
  const sendMessage = useAgentStore((s) => s.sendMessage);

  const [chatMode, setChatMode] = useState(false);
  const [prompt, setPrompt] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  // Reset to the template browser whenever the modal closes.
  useEffect(() => {
    if (!isOpen) setChatMode(false);
  }, [isOpen]);

  // AI generation happens inside this modal: start a fresh conversation and
  // stream the reply in the embedded Copilot instead of navigating away.
  const enterChat = (message: string) => {
    startNewChat();
    setChatMode(true);
    void sendMessage(message, undefined, undefined, 'new-strategy');
  };

  const handleGenerate = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    enterChat(trimmed);
  };

  const handleUseTemplate = (template: StrategyTemplate) => {
    onClose();
    navigate(`/strategies/builder?template=${template.id}`);
  };

  const handleCustomizeWithAI = (template: StrategyTemplate) => {
    enterChat(`Customize the "${template.name}" strategy template for me. ${template.description}`);
  };

  // Expand the in-modal conversation to the full /copilot page — conversation
  // state is shared in the agent store, so it continues seamlessly.
  const handleExpandChat = () => {
    onClose();
    navigate('/copilot');
  };

  const handleStartBlank = () => {
    createNew();
    onClose();
    navigate('/strategies/builder');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div
        className={`relative mx-4 flex w-full flex-col overflow-hidden border-2 border-ink bg-paper shadow-2xl ${
          chatMode ? 'h-[85vh] max-w-[900px]' : 'max-h-[90vh] max-w-[1320px]'
        }`}
      >
        {/* Header */}
        <div className="flex flex-shrink-0 items-center justify-between border-b-2 border-ink px-6 py-4">
          <div>
            <h2 className="font-display text-lg uppercase tracking-tight text-ink">New Strategy</h2>
            <p className="font-mono text-sm text-ink/50">
              {chatMode
                ? 'Copilot is drafting — refine it in the chat'
                : 'Describe it, or pick a template to preview'}
            </p>
          </div>
          <button onClick={onClose} className="p-2 transition-colors hover:bg-ink/5" title="Close">
            <X className="h-5 w-5 text-ink/60" />
          </button>
        </div>

        {chatMode ? (
          <>
            {/* AI-mode toolbar */}
            <div className="flex flex-none items-center justify-between border-b-2 border-ink bg-ink/[0.04] px-6 py-2">
              <button
                onClick={() => setChatMode(false)}
                className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-ink/60 transition-colors hover:text-ink"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Templates
              </button>
              <button
                onClick={handleExpandChat}
                title="Open in full Copilot page"
                className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-ink/60 transition-colors hover:text-ink"
              >
                <Maximize2 className="h-3.5 w-3.5" />
                Expand
              </button>
            </div>
            <CopilotConversation
              variant="modal"
              page="new-strategy"
              fallbackPrompts={[...EXAMPLE_PROMPTS]}
              footerNote="Copilot writes real DSL · runs on your paper account"
              placeholder="Refine — e.g. 'make it monthly' or 'add a 10% gold sleeve'"
              emptyState={
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="grid h-12 w-12 place-items-center border-2 border-ink bg-orange-500 shadow-[3px_3px_0_rgb(var(--lt-ink))]">
                    <Sparkles className="h-6 w-6 text-ink" />
                  </div>
                  <h3 className="mt-4 font-display text-lg uppercase tracking-tight text-ink">
                    Drafting your strategy
                  </h3>
                  <p className="mt-2 max-w-sm text-[13px] text-ink/60">
                    Copilot is turning your description into real DSL. Ask follow-ups to refine it.
                  </p>
                </div>
              }
            />
          </>
        ) : (
          <>
            {/* Copilot command bar */}
            <div className="flex-shrink-0 border-b-2 border-ink bg-ink/[0.04] px-6 py-3.5">
              <div className="flex items-center gap-2">
                <MagicIcon className="h-5 w-5 text-orange-500" />
                <input
                  type="text"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleGenerate(prompt);
                    }
                  }}
                  placeholder='Describe a strategy — e.g. "momentum rotation across the 11 sector ETFs, monthly"'
                  className="input flex-1 font-mono text-sm"
                />
                <button
                  onClick={() => handleGenerate(prompt)}
                  disabled={!prompt.trim()}
                  className="btn btn-primary flex-shrink-0"
                >
                  Generate
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-2">
                {EXAMPLE_PROMPTS.map((example) => (
                  <button
                    key={example}
                    onClick={() => handleGenerate(example)}
                    className="border border-ink/20 px-2 py-1 font-mono text-[11px] text-ink/60 transition-colors hover:border-orange-500 hover:text-ink"
                  >
                    <span className="text-orange-600">↳</span> {example}
                  </button>
                ))}
              </div>
            </div>

            <TemplateBrowser
              onUseTemplate={handleUseTemplate}
              onStartBlank={handleStartBlank}
              onCustomize={handleCustomizeWithAI}
            />
          </>
        )}
      </div>
    </div>
  );
}
