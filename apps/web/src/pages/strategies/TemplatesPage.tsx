/**
 * Strategy Templates — full-page catalog. Same browser as the New Strategy modal
 * (list · preview · DSL), given the whole content width under the app header so
 * the library has room to breathe as it grows.
 */
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { TemplateBrowser } from '../../components/strategies/TemplateBrowser';
import type { StrategyTemplate } from '../../data/strategy-templates';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

export default function TemplatesPage() {
  const navigate = useNavigate();
  const { createNew } = useStrategyBuilderStore();
  const startNewChat = useAgentStore((s) => s.startNewChat);
  const sendMessage = useAgentStore((s) => s.sendMessage);

  const handleUseTemplate = (template: StrategyTemplate) => {
    navigate(`/strategies/builder?template=${template.id}`);
  };

  const handleStartBlank = () => {
    createNew();
    navigate('/strategies/builder');
  };

  const handleCustomize = (template: StrategyTemplate) => {
    startNewChat();
    void sendMessage(
      `Customize the "${template.name}" strategy template for me. ${template.description}`,
      undefined,
      undefined,
      'new-strategy'
    );
    navigate('/copilot');
  };

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col bg-bone">
      {/* Page header */}
      <div className="flex flex-shrink-0 items-center gap-4 border-b-2 border-ink bg-paper px-6 py-3">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-ink/60 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <div className="h-5 w-[2px] bg-ink/15" />
        <div>
          <h1 className="font-display text-lg uppercase leading-none tracking-tight text-ink">
            Strategy Templates
          </h1>
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wide text-ink/50">
            Proven starting points — preview, then deploy or customize
          </p>
        </div>
      </div>

      <TemplateBrowser
        onUseTemplate={handleUseTemplate}
        onStartBlank={handleStartBlank}
        onCustomize={handleCustomize}
      />
    </div>
  );
}
